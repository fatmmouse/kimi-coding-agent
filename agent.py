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
import time

from harness import context as ctx
from harness import interrupt as interrupt_mod
from harness import recovery
from harness.providers import load_env, make_provider
from harness.state import SessionLog, new_session_id
from harness.tools import TOOL_FUNCS, TOOLS

MAX_ROUNDS = 80
# 无工具调用但 todo.md 仍有未完成项时，最多 nudge 续跑几次。
# 防「模型发了句过渡性的话却没调工具」被误判为任务完成（长程任务里真实发生过），也防无限空转。
MAX_CONTINUE_NUDGES = 5

SYSTEM_PROMPT = (
    "You are a coding agent working ONLY inside ./workspace. "
    "Tools: read_file, write_file, edit_file, run_command.\n\n"
    "Workflow on EVERY task:\n"
    "1. PLAN: first write_file a `todo.md` breaking the task into a `- [ ]` checklist.\n"
    "2. EXECUTE the checklist one item at a time, building real, complete artifacts.\n"
    "3. After completing and VERIFYING each item (run it, inspect output), edit_file todo.md "
    "to check it off `- [x]`.\n"
    "4. VERIFY before finishing with run_command (run the code, list files, print outputs).\n"
    "DONE means every `- [ ]` in todo.md is checked off `- [x]` AND verified. "
    "While ANY `- [ ]` remains, you are NOT done—every turn must call a tool to make progress on the next item; "
    "do NOT stop with a plain message like 'next I will do X'. "
    "Only when everything is done AND verified, reply with a short final message and call NO tool."
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
        self._continue_nudges = 0  # 完成判定 nudge 计数（见主循环 no-tool 分支）
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
            # ---- 时间维度（题眼是「2 小时」，时间是第一指标）----
            "wall_total": 0.0,      # 总墙钟耗时（秒）
            "per_round_wall": [],   # 每轮耗时
            "api_time": 0.0,        # 纯 LLM 调用耗时（不含重试等待）
            "tool_time": 0.0,       # 工具执行耗时
            "compact_time": 0.0,    # 上下文压缩耗时（这是 overhead）
            "retry_wait": 0.0,      # 重试退避等待累计
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

    def _todo_has_open_items(self) -> bool:
        """todo.md 里是否还有未打勾的 `- [ ]`——完成判定的 ground truth。"""
        from harness.tools import WORKSPACE
        todo = WORKSPACE / "todo.md"
        if not todo.exists():
            return False
        return "- [ ]" in todo.read_text(encoding="utf-8", errors="ignore")

    # ---------- 主循环 ----------
    def run(self):
        self.load()
        self._install_sigint()
        self.steering.start()

        last_input_tokens = 0
        wall_start = time.monotonic()
        for i in range(self.start_round + 1, self.max_rounds + 1):
            if self._sigint:
                print("[中断] 已在安全点优雅停止。")
                break
            round_t0 = time.monotonic()

            self._drain_steering()
            self._scripted_steer(i)
            self._maybe_compact(last_input_tokens)

            approx = ctx.estimate_tokens(self.messages)
            print(f"\n{'#'*60}\n# ROUND {i:02d}  messages={len(self.messages)}  approx_tokens≈{approx}\n{'#'*60}")

            def _on_retry(a, d, e):
                self.metrics["retries"] += 1
                self.metrics["retry_wait"] += d
                print(f"  [retry] 第 {a} 次重试，{d:.1f}s 后（{type(e).__name__}）")

            api_t0 = time.monotonic()
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
            # 纯 API 时间 = 整段耗时 - 本轮退避等待
            self.metrics["api_time"] += (time.monotonic() - api_t0)

            last_input_tokens = resp.usage.input
            self.metrics["input_tokens"].append(resp.usage.input)
            self.metrics["rounds"] = i
            self.messages.append(resp.assistant_msg)
            self.log.append("message", {"message": resp.assistant_msg})
            self.log.append("round", {"n": i})
            print(f"[usage] input={resp.usage.input} output={resp.usage.output}")

            if not resp.tool_calls:
                # 完成判定：没调工具 ≠ 任务真完成。模型可能只是发了句过渡性的话
                # （「接下来我去做 X」）。用 todo.md 这个语义状态层做 ground truth——
                # 还有未打勾项就 nudge 续跑，连续 nudge 到上限仍不动手才真正收尾（防空转）。
                if self._todo_has_open_items() and self._continue_nudges < MAX_CONTINUE_NUDGES:
                    self._continue_nudges += 1
                    nudge = {"role": "user", "content":
                             "[继续] todo.md 里还有未打勾的项没做完。请直接调用工具继续处理下一个未完成项，"
                             "不要只回复一句话。某项确实做不了就在 todo.md 注明原因再跳过。"}
                    self.messages.append(nudge)
                    self.log.append("message", {"message": nudge})
                    self.metrics["per_round_wall"].append(round(time.monotonic() - round_t0, 2))
                    print(f"  [continue] todo 仍有未完成项，nudge 续跑（{self._continue_nudges}/{MAX_CONTINUE_NUDGES}）")
                    continue
                self.metrics["completed"] = True
                self.metrics["per_round_wall"].append(round(time.monotonic() - round_t0, 2))
                print(f"\n[FINAL]\n{resp.text}")
                break

            self._continue_nudges = 0  # 模型又动手了，恢复 nudge 预算
            tool_t0 = time.monotonic()
            self._run_tools(resp.tool_calls)
            self.metrics["tool_time"] += (time.monotonic() - tool_t0)

            self.metrics["per_round_wall"].append(round(time.monotonic() - round_t0, 2))

            if self._crash_after and i >= self._crash_after:
                # 模拟进程被 kill -9：不走任何清理，直接消失。
                # JSONL 已逐行 flush+fsync，所以状态留在磁盘，resume 可恢复。
                self.metrics["crashed"] = True
                print(f"  [chaos] 模拟崩溃：第 {i} 轮后进程被强杀")
                import os
                os._exit(137)
        else:
            print(f"\n[到达 MAX_ROUNDS={self.max_rounds}，强制停止]")

        # retry_wait 算在 api_time 里了，扣出来归到独立桶
        self.metrics["api_time"] = round(self.metrics["api_time"] - self.metrics["retry_wait"], 2)
        self.metrics["retry_wait"] = round(self.metrics["retry_wait"], 2)
        self.metrics["tool_time"] = round(self.metrics["tool_time"], 2)
        self.metrics["compact_time"] = round(self.metrics["compact_time"], 2)
        self.metrics["wall_total"] = round(time.monotonic() - wall_start, 2)

        self.steering.stop()
        self.log.close()
        self._print_time_profile()
        print(f"\n[会话 {self.session_id} 结束] resume: python agent.py --resume {self.session_id}")
        return self.metrics

    def _print_time_profile(self):
        """时间画像 + 2 小时外推——直接回应题目的「连续执行 2 小时」。"""
        m = self.metrics
        wall = m["wall_total"] or 1e-9
        rounds = m["rounds"] or 1
        per_round = wall / rounds
        proj_2h = int(7200 / per_round) if per_round > 0 else 0
        def pct(x):
            return f"{x:6.1f}s ({100*x/wall:4.1f}%)"
        print(f"\n{'='*60}\n[时间画像]  总耗时 {wall:.1f}s / {rounds} 轮  (avg {per_round:.1f}s/轮)")
        print(f"  纯 LLM 调用 : {pct(m['api_time'])}")
        print(f"  工具执行    : {pct(m['tool_time'])}")
        print(f"  上下文压缩  : {pct(m['compact_time'])}   <- overhead")
        print(f"  重试等待    : {pct(m['retry_wait'])}")
        print(f"  按此速率，连续跑 2 小时 ≈ 可执行 {proj_2h} 轮")
        print(f"{'='*60}")

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
        t0 = time.monotonic()
        new_msgs, usage = ctx.compact(self.messages, self.provider)
        if new_msgs is None:
            return
        self.metrics["compact_time"] += (time.monotonic() - t0)
        self.messages = new_msgs
        self.metrics["compactions"] += 1
        self.log.append("compaction", {"messages": new_msgs})
        after = ctx.estimate_tokens(self.messages)
        print(f"  [compact] 历史压缩 {before}→{after} tokens（约 -{before-after}），耗时 {time.monotonic()-t0:.1f}s")


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
