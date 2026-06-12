"""评测集：场景 × ablation 矩阵。每个机制开/关跑同一任务，用数据证明它的价值。

跑法：
    .venv/bin/python -m evals.scenarios                 # 全部场景，默认 kimi
    .venv/bin/python -m evals.scenarios --model deepseek
    .venv/bin/python -m evals.scenarios --only S2 S5    # 只跑指定场景

输出：evals/results/summary.csv + 终端表格。每个数字都可由此脚本复现。

设计：S1/S2/S4/S5 在进程内跑（快、能直接拿 metrics）；S3 必须用子进程，
因为它用 os._exit 模拟 kill -9——在进程内会把 runner 一起杀掉。子进程崩溃后，
靠 append-only 的 events.jsonl 落盘状态，resume 子进程接着跑完。
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.providers import load_env  # noqa: E402

RESULTS = ROOT / "evals" / "results"
WORKSPACE = ROOT / "workspace"
SESSIONS = ROOT / "agent_sessions_unused"  # 占位，真正路径见 .agent
AGENT_DIR = ROOT / ".agent"


def _clean():
    for p in (WORKSPACE, AGENT_DIR):
        shutil.rmtree(p, ignore_errors=True)


def run_inproc(model, task, **hooks):
    """进程内跑一次，返回 metrics dict（失败则 completed=False）。"""
    _clean()
    from agent import Agent  # 延迟导入，确保 _clean 后 workspace 重建
    args = SimpleNamespace(
        task=task, model=model, resume=None,
        no_compact=hooks.get("no_compact", False),
        no_resume=hooks.get("no_resume", False),
        no_retry=hooks.get("no_retry", False),
        no_interrupt=hooks.get("no_interrupt", False),
        max_rounds=hooks.get("max_rounds", 30),
        context_window=hooks.get("context_window"),
        crash_after=None,
        steer_at=hooks.get("steer_at", {}),
        chaos=hooks.get("chaos"),
    )
    try:
        m = Agent(args).run()
    except Exception as e:  # noqa: BLE001 —— retry-off 时故障会冒出来，正是要观察的
        m = {"completed": False, "rounds": 0, "input_tokens": [], "compactions": 0,
             "retries": 0, "tool_fails": 0, "error": f"{type(e).__name__}: {e}"}
    return m


def run_subproc(model, extra_args, expect_crash=False):
    """子进程跑一次。返回 (exit_code, metrics_or_None)。"""
    metrics_path = AGENT_DIR / "eval_metrics.json"
    metrics_path.unlink(missing_ok=True)
    cmd = [sys.executable, str(ROOT / "agent.py"), "--model", model,
           "--metrics-out", str(metrics_path)] + extra_args
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    metrics = None
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    return r.returncode, metrics


# ════════════════════════════ 场景定义 ════════════════════════════

def s1_context(model):
    """S1 上下文管理：小窗口强制压缩，对比 compact on/off 的输入 token 增长。"""
    task = ("依次创建 a.py b.py c.py d.py 四个文件，每个文件写一个不同的函数并各自 run_command 运行验证，"
            "最后创建 main.py 依次调用四个函数并运行。每完成一个就在 todo.md 打勾。")
    rows = []
    for label, no_compact in [("compact_on", False), ("compact_off", True)]:
        m = run_inproc(model, task, no_compact=no_compact, context_window=3000, max_rounds=24)
        toks = m["input_tokens"] or [0]
        rows.append({
            "scenario": "S1_context", "variant": label, "completed": m["completed"],
            "rounds": m["rounds"], "peak_input_tokens": max(toks),
            "final_input_tokens": toks[-1], "compactions": m["compactions"], "note": "",
        })
    return rows


def s2_retry(model):
    """S2 失败恢复：第一次 API 调用必失败 + 后续概率失败，对比 retry on/off。"""
    task = "写一个 fizzbuzz.py 打印 1..15 并运行验证。"
    rows = []
    for label, no_retry in [("retry_on", False), ("retry_off", True)]:
        chaos = {"fail_first_n": 1, "error_probability": 0.25, "seed": 7}
        m = run_inproc(model, task, no_retry=no_retry, chaos=chaos, max_rounds=12)
        rows.append({
            "scenario": "S2_retry", "variant": label, "completed": m["completed"],
            "rounds": m["rounds"], "peak_input_tokens": max(m["input_tokens"] or [0]),
            "final_input_tokens": (m["input_tokens"] or [0])[-1], "compactions": 0,
            "note": m.get("error", "") or f"retries={m['retries']}",
        })
    return rows


def s3_resume(model):
    """S3 任务状态：子进程跑到第 2 轮 kill -9，resume 子进程接着跑完（不重做）。"""
    task = ("创建 step1.py 打印 step1 并运行；再创建 step2.py 打印 step2 并运行；"
            "再创建 step3.py 打印 step3 并运行。每步完成在 todo.md 打勾。")
    rows = []

    # 基线：一口气跑完，量出整任务需要多少轮（代表「不 resume、从头重跑」的成本）
    _clean()
    base = run_inproc(model, task, max_rounds=20)
    baseline_rounds = base["rounds"]

    # 崩溃 run：第 2 轮后 os._exit(137)
    _clean()
    code1, _ = run_subproc(model, [task, "--crash-after", "2", "--max-rounds", "20"], expect_crash=True)
    # 找到崩溃留下的会话 id
    sess_dirs = sorted((AGENT_DIR / "sessions").glob("*"))
    sid = sess_dirs[-1].name if sess_dirs else None
    events_before = len((AGENT_DIR / "sessions" / sid / "events.jsonl").read_text().splitlines()) if sid else 0

    # resume run：接着跑完
    code2, m2 = run_subproc(model, ["--resume", sid, "--max-rounds", "20"]) if sid else (1, None)
    resume_completed = bool(m2 and m2.get("completed"))
    resume_total_rounds = m2["rounds"] if m2 else 0

    rows.append({
        "scenario": "S3_resume", "variant": "resume_on", "completed": resume_completed,
        "rounds": resume_total_rounds, "peak_input_tokens": 0, "final_input_tokens": 0,
        "compactions": 0,
        "note": f"crash_exit={code1};从断点续到第{resume_total_rounds}轮完成;崩溃前已落盘{events_before}事件",
    })
    rows.append({
        "scenario": "S3_resume", "variant": "no_resume(baseline)", "completed": base["completed"],
        "rounds": baseline_rounds, "peak_input_tokens": 0, "final_input_tokens": 0,
        "compactions": 0, "note": f"从头跑完需{baseline_rounds}轮（崩溃后不resume就要重付这些）",
    })
    return rows


def s4_tool_fail(model):
    """S4 工具失败自纠：任务里埋一个必失败命令，看模型能否从错误里恢复并完成。"""
    task = ("先 run_command 执行 `python nonexistent_xyz.py`（它会失败）；"
            "看到失败后，改为创建 hello.py 打印 hello 并成功运行它。")
    m = run_inproc(model, task, max_rounds=12)
    return [{
        "scenario": "S4_tool_fail", "variant": "self_correct", "completed": m["completed"],
        "rounds": m["rounds"], "peak_input_tokens": max(m["input_tokens"] or [0]),
        "final_input_tokens": (m["input_tokens"] or [0])[-1], "compactions": 0,
        "note": f"tool_fails={m['tool_fails']}（>0 且 completed 即为成功自纠）",
    }]


def s5_interrupt(model):
    """S5 用户中断转向：第 2 轮注入「改打印 Goodbye」，看产物是否采纳。"""
    task = "创建 greet.py，让它打印 Hello，然后运行验证。"
    rows = []
    # on：运行中注入改需求
    m_on = run_inproc(model, task, steer_at={2: "改主意了：让 greet.py 打印 Goodbye 而不是 Hello。"},
                      max_rounds=12)
    greet = (WORKSPACE / "greet.py").read_text() if (WORKSPACE / "greet.py").exists() else ""
    adopted = "Goodbye" in greet
    rows.append({
        "scenario": "S5_interrupt", "variant": "steer_on", "completed": m_on["completed"],
        "rounds": m_on["rounds"], "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        "note": f"注入改需求后产物含Goodbye={adopted}",
    })
    # off：不注入，应保持 Hello
    m_off = run_inproc(model, task, max_rounds=12)
    greet2 = (WORKSPACE / "greet.py").read_text() if (WORKSPACE / "greet.py").exists() else ""
    rows.append({
        "scenario": "S5_interrupt", "variant": "steer_off(baseline)", "completed": m_off["completed"],
        "rounds": m_off["rounds"], "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        "note": f"无注入产物含Hello={'Hello' in greet2}",
    })
    return rows


SCENARIOS = {
    "S1": s1_context, "S2": s2_retry, "S3": s3_resume, "S4": s4_tool_fail, "S5": s5_interrupt,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="kimi")
    ap.add_argument("--only", nargs="*", default=list(SCENARIOS))
    args = ap.parse_args()

    load_env()
    RESULTS.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for key in args.only:
        fn = SCENARIOS[key]
        print(f"\n{'='*70}\n运行场景 {key}（model={args.model}）\n{'='*70}")
        all_rows.extend(fn(args.model))

    # 落盘 CSV
    out = RESULTS / f"summary_{args.model}.csv"
    fields = ["scenario", "variant", "completed", "rounds", "peak_input_tokens",
              "final_input_tokens", "compactions", "note"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    # 终端表格
    print(f"\n{'='*70}\n评测结果汇总（model={args.model}）→ {out}\n{'='*70}")
    for r in all_rows:
        print(f"  {r['scenario']:14s} {r['variant']:22s} done={str(r['completed']):5s} "
              f"rounds={r['rounds']:2d} peak_tok={r['peak_input_tokens']:6d}  {r['note']}")
    _clean()


if __name__ == "__main__":
    main()
