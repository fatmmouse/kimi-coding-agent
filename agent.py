#!/usr/bin/env python3
"""可连续执行长任务的 coding agent —— 主循环 + 四个机制的接线。

每个机制都做成可开关的 ablation flag，这样评测时同一份代码开/关对比，
每个机制的价值都有控制变量的数据，而不是空谈。

  python agent.py "任务描述"                  # 全机制开启，默认 kimi
  python agent.py --model deepseek "任务"      # 换 provider
  python agent.py --resume 20260612-153000     # 从某会话续跑
  python agent.py --no-compact "任务"          # 关掉机制① 看上下文如何膨胀
  python agent.py --no-resume  ...             # 关掉机制② 的重放
  python agent.py --no-retry   ...             # 关掉机制③ 的重试
  python agent.py --no-interrupt ...           # 关掉机制④
"""

from __future__ import annotations

import argparse
import json
import signal
import sys

from harness import context as ctx
from harness import interrupt as interrupt_mod
from harness import recovery
from harness.providers import load_env, make_provider
from harness.state import SessionLog, new_session_id
from harness.tools import TOOL_FUNCS, TOOLS

MAX_ROUNDS = 80

SYSTEM_PROMPT = (
    "You are a coding agent working ONLY inside ./workspace. "
    "Tools: read_file, write_file, edit_file, run_command.\n\n"
    "Workflow on EVERY task:\n"
    "1. PLAN: first write_file a `todo.md` breaking the task into a `- [ ]` checklist.\n"
    "2. EXECUTE the checklist one item at a time, building real, complete artifacts.\n"
    "3. After completing and VERIFYING each item (run it, inspect output), edit_file todo.md "
    "to check it off `- [x]`.\n"
    "4. VERIFY before finishing with run_command (run the code, list files, print outputs).\n"
    "DONE means every item is done AND verified. Then reply with a short final message and call NO tool."
)


class Agent:
    def __init__(self, args):
        self.args = args
        self.provider = make_provider(args.model)
        self.compact_on = not args.no_compact
        self.retry_on = not args.no_retry
        self.guard = recovery.LoopGuard()
        self.steering = interrupt_mod.StdinSteering(enabled=not args.no_interrupt)
        self._sigint = 0
        # ---- 评测钩子（CLI 不暴露，评测脚本经 SimpleNamespace 注入）----
        self.max_rounds = getattr(args, "max_rounds", MAX_ROUNDS)
        self.context_window = getattr(args, "context_window", None) or self.provider.context_window
        self._crash_after = getattr(args, "crash_after", None)   # 第 K 轮后 os._exit 模拟崩溃
        self._steer_at = getattr(args, "steer_at", {}) or {}      # {round_no: "插话内容"}
        chaos = getattr(args, "chaos", None)                      # 故障注入配置 dict
        if chaos:
            from evals.chaos import ChaosProvider
            self.provider = ChaosProvider(self.provider, **chaos)
        self.metrics = {
            "completed": False, "rounds": 0, "input_tokens": [],
            "compactions": 0, "retries": 0, "tool_fails": 0, "crashed": False,
        }

    # ---------- 会话装载：新建或 resume ----------
    def load(self):
        if self.args.resume and not self.args.no_resume:
            self.session_id = self.args.resume
            self.messages, meta = SessionLog.replay(self.session_id)
            self.task = meta.get("task", "")
            self.start_round = meta.get("rounds", 0)
            self.log = SessionLog(self.session_id, resume=True)
            # 中断即上下文：让模型知道这是续跑
            self.messages.append({
                "role": "user",
                "content": "[本会话由先前中断的会话续接。先读 workspace/todo.md 看做到哪了，从断点继续，不要重做已完成项。]",
            })
            print(f"[resume] 会话 {self.session_id}，已重放 {len(self.messages)} 条消息，从第 {self.start_round+1} 轮继续")
        else:
            self.session_id = new_session_id()
            self.task = self.args.task
            self.start_round = 0
            self.log = SessionLog(self.session_id)
            self.log.append("meta", {"data": {"task": self.task, "model": self.provider.model}})
            self.messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self.task},
            ]
            for m in self.messages:
                self.log.append("message", {"message": m})
            print(f"[new] 会话 {self.session_id}  model={self.provider.model}")

    # ---------- 安全点：处理 Ctrl-C 与 steering ----------
    def _install_sigint(self):
        def handler(signum, frame):
            self._sigint += 1
            if self._sigint == 1:
                print(f"\n[中断] 已请求优雅停止——当前轮结束后落盘退出。再按一次 Ctrl-C 立即强退。"
                      f"\n        resume 命令：python agent.py --resume {self.session_id}")
            else:
                print("\n[强退] append-only 日志已保证状态不丢。")
                self.log.close()
                sys.exit(130)
        signal.signal(signal.SIGINT, handler)

    def _drain_steering(self):
        """安全点注入 steering 消息（中断即上下文）。"""
        for line in self.steering.drain():
            self._inject_steer(line)

    def _scripted_steer(self, round_no: int):
        """评测用：在预设轮注入一条 steering 消息，模拟用户运行中插话。"""
        if round_no in self._steer_at:
            self._inject_steer(self._steer_at[round_no])

    def _inject_steer(self, line: str):
        msg = {"role": "user", "content": f"[用户运行中插话] {line}"}
        self.messages.append(msg)
        self.log.append("message", {"message": msg})
        print(f"[steering] 已注入: {line}")

    # ---------- 主循环 ----------
    def run(self):
        self.load()
        self._install_sigint()
        self.steering.start()

        last_input_tokens = 0
        for i in range(self.start_round + 1, self.max_rounds + 1):
            if self._sigint:
                print("[中断] 已在安全点优雅停止。")
                break

            self._drain_steering()
            self._scripted_steer(i)
            self._maybe_compact(last_input_tokens)

            approx = ctx.estimate_tokens(self.messages)
            print(f"\n{'#'*60}\n# ROUND {i:02d}  messages={len(self.messages)}  approx_tokens≈{approx}\n{'#'*60}")

            def _on_retry(a, d, e):
                self.metrics["retries"] += 1
                print(f"  [retry] 第 {a} 次重试，{d:.1f}s 后（{type(e).__name__}）")

            try:
                resp = recovery.with_retry(
                    lambda: self.provider.chat(self.messages, TOOLS),
                    enabled=self.retry_on,
                    on_attempt=_on_retry,
                )
            except recovery.ContextOverflow:
                print("  [overflow] 上下文超窗，紧急压缩后重试本轮")
                if self.compact_on:
                    self._force_compact()
                continue

            last_input_tokens = resp.usage.input
            self.metrics["input_tokens"].append(resp.usage.input)
            self.metrics["rounds"] = i
            self.messages.append(resp.assistant_msg)
            self.log.append("message", {"message": resp.assistant_msg})
            self.log.append("round", {"n": i})
            print(f"[usage] input={resp.usage.input} output={resp.usage.output}")

            if not resp.tool_calls:
                self.metrics["completed"] = True
                print(f"\n[FINAL]\n{resp.text}")
                break

            self._run_tools(resp.tool_calls)

            if self._crash_after and i >= self._crash_after:
                # 模拟进程被 kill -9：不走任何清理，直接消失。
                # JSONL 已逐行 flush+fsync，所以状态留在磁盘，resume 可恢复。
                self.metrics["crashed"] = True
                print(f"  [chaos] 模拟崩溃：第 {i} 轮后进程被强杀")
                import os
                os._exit(137)
        else:
            print(f"\n[到达 MAX_ROUNDS={self.max_rounds}，强制停止]")

        self.steering.stop()
        self.log.close()
        print(f"\n[会话 {self.session_id} 结束] resume: python agent.py --resume {self.session_id}")
        return self.metrics

    def _run_tools(self, tool_calls):
        for tc in tool_calls:
            # 死循环防呆
            warn = self.guard.check_repeat(tc.name, tc.arguments)
            if warn:
                self._tool_result(tc.id, warn, ok=False)
                continue
            # 危险命令审批门
            if tc.name == "run_command" and interrupt_mod.is_dangerous(tc.arguments.get("cmd", "")):
                if not self._approve(tc.arguments["cmd"]):
                    self._tool_result(tc.id, "[用户拒绝了这条危险命令。换个安全的做法。]", ok=False)
                    continue
            # 执行：工具异常永不冒泡，转成错误文本回喂
            print(f"  >>> {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)[:120]})")
            try:
                raw = TOOL_FUNCS[tc.name](**tc.arguments)
                ok = not (tc.name == "run_command" and raw.startswith("exit=") and "exit=0" not in raw.split("\n")[0])
            except Exception as e:  # noqa: BLE001
                raw = f"[工具错误] {type(e).__name__}: {e}"
                ok = False
            if not ok:
                self.metrics["tool_fails"] += 1
            result = ctx.offload_tool_result(raw, tc.name)
            self._tool_result(tc.id, result, ok=ok)
            # 连续失败熔断
            fuse = self.guard.record_tool_outcome(ok)
            if fuse:
                self.messages.append({"role": "user", "content": fuse})
                self.log.append("message", {"message": self.messages[-1]})

    def _tool_result(self, call_id, content, ok):
        msg = {"role": "tool", "tool_call_id": call_id, "content": content}
        self.messages.append(msg)
        self.log.append("message", {"message": msg})
        flag = "" if ok else "  [FAIL]"
        print(f"      result{flag}: {content.splitlines()[0][:100] if content else ''}")

    def _approve(self, cmd: str) -> bool:
        if not (sys.stdin and sys.stdin.isatty()):
            print(f"  [审批] 非交互环境，默认拒绝危险命令: {cmd}")
            return False
        ans = input(f"  [审批] 危险命令 `{cmd}` —— 执行吗？(y/N) ").strip().lower()
        return ans == "y"

    # ---------- 机制①：按需压缩 ----------
    def _maybe_compact(self, last_input_tokens):
        if not self.compact_on:
            return
        approx = ctx.estimate_tokens(self.messages)
        signal_tokens = max(last_input_tokens, approx)
        if signal_tokens >= self.context_window * ctx.TRIGGER_RATIO:
            self._force_compact()

    def _force_compact(self):
        before = ctx.estimate_tokens(self.messages)
        new_msgs, usage = ctx.compact(self.messages, self.provider)
        if new_msgs is None:
            return
        self.messages = new_msgs
        self.metrics["compactions"] += 1
        self.log.append("compaction", {"messages": new_msgs})
        after = ctx.estimate_tokens(self.messages)
        print(f"  [compact] 历史压缩 {before}→{after} tokens（约 -{before-after}）")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task", nargs="?", default="")
    p.add_argument("--model", default="kimi", help="kimi | deepseek")
    p.add_argument("--resume", default=None, help="会话 id")
    p.add_argument("--no-compact", action="store_true")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--no-retry", action="store_true")
    p.add_argument("--no-interrupt", action="store_true")
    # 评测钩子（给 evals/ 用；日常使用不必关心）
    p.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    p.add_argument("--context-window", type=int, default=None)
    p.add_argument("--crash-after", type=int, default=None)
    p.add_argument("--steer-json", default=None, help='JSON {"轮号": "插话"}')
    p.add_argument("--chaos-json", default=None, help="JSON 故障注入配置")
    p.add_argument("--metrics-out", default=None, help="把 metrics 落盘到此路径")
    args = p.parse_args()
    if args.steer_json:
        args.steer_at = {int(k): v for k, v in json.loads(args.steer_json).items()}
    if args.chaos_json:
        args.chaos = json.loads(args.chaos_json)

    if not args.task and not args.resume:
        p.error("需要任务描述，或用 --resume <id> 续跑")

    load_env()
    agent = Agent(args)
    metrics = agent.run()
    if getattr(args, "metrics_out", None) and metrics is not None:
        from pathlib import Path
        Path(args.metrics_out).write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
