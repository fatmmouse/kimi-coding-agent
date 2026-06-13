"""评测集：场景 × ablation 矩阵 + 硬任务马拉松。每个机制开/关跑同一任务，用数据证明价值。

跑法：
    .venv/bin/python -m evals.scenarios                 # 全部场景，默认 kimi
    .venv/bin/python -m evals.scenarios --model deepseek
    .venv/bin/python -m evals.scenarios --only S6       # 只跑马拉松

输出：evals/results/summary_<model>.csv + 终端表格。每个数字都可复现。

时间是第一指标——题眼是「连续执行 2 小时」。每个场景都记录墙钟耗时、各阶段占比、
以及「按此速率 2 小时能执行多少轮」的外推。硬任务（S1 升级版、S6 马拉松）用 pytest 全绿做完成判据，
能压出真实瓶颈（调试迭代、压缩 overhead、上下文增长）。

S1/S2/S4/S5 进程内跑；S3 用子进程（os._exit 模拟 kill -9，进程内会连 runner 一起杀）。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
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
AGENT_DIR = ROOT / ".agent"
VENV_BIN = ROOT / ".venv" / "bin"


def _clean():
    for p in (WORKSPACE, AGENT_DIR):
        shutil.rmtree(p, ignore_errors=True)


def _timecols(m: dict) -> dict:
    """从 metrics 抽出时间维度列 + 2 小时外推。"""
    wall = m.get("wall_total", 0) or 0
    rounds = m.get("rounds", 0) or 0
    proj = int(7200 / (wall / rounds)) if wall > 0 and rounds > 0 else 0
    return {
        "wall_s": round(wall, 1), "api_s": m.get("api_time", 0), "tool_s": m.get("tool_time", 0),
        "compact_s": m.get("compact_time", 0), "retry_s": m.get("retry_wait", 0),
        "proj_2h_rounds": proj,
    }


def pytest_passes(workspace: Path) -> tuple[bool, str]:
    """在 workspace 跑 pytest，返回 (是否全绿且有用例, 末行摘要)。硬任务的完成判据。"""
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=workspace,
                           capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        return False, f"pytest run error: {e}"
    out = (r.stdout + r.stderr).strip()
    last = out.splitlines()[-1] if out else "(no output)"
    return (r.returncode == 0 and "passed" in out), last


def run_inproc(model, task, **hooks):
    _clean()
    from agent import Agent
    args = SimpleNamespace(
        task=task, model=model, resume=None,
        no_compact=hooks.get("no_compact", False), no_resume=hooks.get("no_resume", False),
        no_retry=hooks.get("no_retry", False), no_interrupt=hooks.get("no_interrupt", False),
        max_rounds=hooks.get("max_rounds", 30), context_window=hooks.get("context_window"),
        crash_after=None, steer_at=hooks.get("steer_at", {}), chaos=hooks.get("chaos"),
    )
    try:
        m = Agent(args).run()
    except Exception as e:  # noqa: BLE001
        m = {"completed": False, "rounds": 0, "input_tokens": [], "compactions": 0,
             "retries": 0, "tool_fails": 0, "error": f"{type(e).__name__}: {e}"}
    return m


def run_subproc(model, extra_args):
    metrics_path = AGENT_DIR / "eval_metrics.json"
    metrics_path.unlink(missing_ok=True)
    cmd = [sys.executable, str(ROOT / "agent.py"), "--model", model,
           "--metrics-out", str(metrics_path)] + extra_args
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else None
    return r.returncode, metrics


# ════════════════════════════ 任务库 ════════════════════════════

CALC_TASK = (
    "实现一个算术表达式求值器，拆成多个文件："
    "tokenizer.py（把如 '3 + 4 * (2 - 1)' 的字符串切成 token 列表）；"
    "parser.py（递归下降解析，正确处理 + - * / 的优先级和括号）；"
    "evaluator.py（对解析结果求值，除以零要抛出清晰错误）。"
    "再写 test_calc.py 用 pytest 覆盖：运算优先级、括号嵌套、除零、多位数、负数。"
    "用 `python -m pytest -q` 运行，必须全部通过。每完成一个文件就在 todo.md 打勾。"
)

KV_TASK = (
    "从零实现一个支持持久化的内存 KV store，这是个完整的小项目，请认真拆解后逐步实现："
    "store.py（SET/GET/DEL/KEYS 四个操作，且每个 key 可带 TTL 秒数，过期后 GET 返回不存在）；"
    "persist.py（把写操作以 append-only 日志写到 data.log，进程重启时能重放 data.log 恢复全部未过期数据）；"
    "cli.py（一个读取命令的循环，支持上述命令）。"
    "再写 test_store.py 和 test_persist.py 用 pytest 覆盖："
    "基本读写删、KEYS 列举、TTL 过期、append-only 持久化后重新加载能恢复数据、过期数据不被恢复。"
    "用 `python -m pytest -q` 运行，必须全部通过。"
    "先写 todo.md 拆解任务，每完成一项打勾，最后跑全部测试确认全绿。"
)


# ════════════════════════════ 场景 ════════════════════════════

def s1_context(model):
    """S1 上下文管理（硬任务）：求值器 + 测试，小窗口强制多次压缩，对比 compact on/off。"""
    rows = []
    for label, no_compact in [("compact_on", False), ("compact_off", True)]:
        m = run_inproc(model, CALC_TASK, no_compact=no_compact, context_window=5000, max_rounds=35)
        passed, last = pytest_passes(WORKSPACE)
        toks = m["input_tokens"] or [0]
        rows.append({
            "scenario": "S1_context", "variant": label, "completed": passed,
            "rounds": m["rounds"], "peak_input_tokens": max(toks), "final_input_tokens": toks[-1],
            "compactions": m["compactions"], **_timecols(m), "note": f"pytest: {last}",
        })
    return rows


def s2_retry(model):
    """S2 失败恢复：首次 API 调用必失败 + 后续概率失败，对比 retry on/off。"""
    task = "写一个 fizzbuzz.py 打印 1..15 并运行验证。"
    rows = []
    for label, no_retry in [("retry_on", False), ("retry_off", True)]:
        chaos = {"fail_first_n": 1, "error_probability": 0.25, "seed": 7}
        m = run_inproc(model, task, no_retry=no_retry, chaos=chaos, max_rounds=12)
        rows.append({
            "scenario": "S2_retry", "variant": label, "completed": m["completed"],
            "rounds": m["rounds"], "peak_input_tokens": max(m["input_tokens"] or [0]),
            "final_input_tokens": (m["input_tokens"] or [0])[-1], "compactions": 0,
            **_timecols(m), "note": m.get("error", "") or f"retries={m['retries']}",
        })
    return rows


def s3_resume(model):
    """S3 任务状态：子进程跑到第 2 轮 kill -9，resume 子进程接着跑完（不重做）。"""
    task = ("创建 step1.py 打印 step1 并运行；再创建 step2.py 打印 step2 并运行；"
            "再创建 step3.py 打印 step3 并运行。每步完成在 todo.md 打勾。")
    rows = []
    _clean()
    base = run_inproc(model, task, max_rounds=20)
    baseline_rounds = base["rounds"]

    _clean()
    code1, _ = run_subproc(model, [task, "--crash-after", "2", "--max-rounds", "20"])
    sess_dirs = sorted((AGENT_DIR / "sessions").glob("*"))
    sid = sess_dirs[-1].name if sess_dirs else None
    events_before = len((AGENT_DIR / "sessions" / sid / "events.jsonl").read_text().splitlines()) if sid else 0

    code2, m2 = run_subproc(model, ["--resume", sid, "--max-rounds", "20"]) if sid else (1, None)
    resume_completed = bool(m2 and m2.get("completed"))
    resume_rounds = m2["rounds"] if m2 else 0
    t = _timecols(m2 or {})

    rows.append({
        "scenario": "S3_resume", "variant": "resume_on", "completed": resume_completed,
        "rounds": resume_rounds, "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        **t, "note": f"crash_exit={code1};续到第{resume_rounds}轮完成;崩溃前落盘{events_before}事件",
    })
    rows.append({
        "scenario": "S3_resume", "variant": "no_resume(baseline)", "completed": base["completed"],
        "rounds": baseline_rounds, "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        **_timecols(base), "note": f"从头跑完需{baseline_rounds}轮（崩溃不resume就重付）",
    })
    return rows


def s4_tool_fail(model):
    """S4 工具失败自纠：埋一个必失败命令，看模型能否恢复并完成。"""
    task = ("先 run_command 执行 `python nonexistent_xyz.py`（它会失败）；"
            "看到失败后，改为创建 hello.py 打印 hello 并成功运行它。")
    m = run_inproc(model, task, max_rounds=12)
    return [{
        "scenario": "S4_tool_fail", "variant": "self_correct", "completed": m["completed"],
        "rounds": m["rounds"], "peak_input_tokens": max(m["input_tokens"] or [0]),
        "final_input_tokens": (m["input_tokens"] or [0])[-1], "compactions": 0,
        **_timecols(m), "note": f"tool_fails={m['tool_fails']}（>0 且 completed 即成功自纠）",
    }]


def s5_interrupt(model):
    """S5 用户中断转向：第 2 轮注入「改打印 Goodbye」，看产物是否采纳。"""
    task = "创建 greet.py，让它打印 Hello，然后运行验证。"
    rows = []
    m_on = run_inproc(model, task, steer_at={2: "改主意了：让 greet.py 打印 Goodbye 而不是 Hello。"}, max_rounds=12)
    greet = (WORKSPACE / "greet.py").read_text() if (WORKSPACE / "greet.py").exists() else ""
    rows.append({
        "scenario": "S5_interrupt", "variant": "steer_on", "completed": m_on["completed"],
        "rounds": m_on["rounds"], "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        **_timecols(m_on), "note": f"注入改需求后产物含Goodbye={'Goodbye' in greet}",
    })
    m_off = run_inproc(model, task, max_rounds=12)
    greet2 = (WORKSPACE / "greet.py").read_text() if (WORKSPACE / "greet.py").exists() else ""
    rows.append({
        "scenario": "S5_interrupt", "variant": "steer_off(baseline)", "completed": m_off["completed"],
        "rounds": m_off["rounds"], "peak_input_tokens": 0, "final_input_tokens": 0, "compactions": 0,
        **_timecols(m_off), "note": f"无注入产物含Hello={'Hello' in greet2}",
    })
    return rows


def s6_marathon(model):
    """S6 马拉松（压轴）：完整 KV store + 持久化 + 恢复 + pytest。全机制开，真实跑到底。
    重点不是 ablation，是在一个真有难度的任务上看：能不能跑完、时间花在哪、瓶颈在哪、2h 外推。"""
    m = run_inproc(model, KV_TASK, context_window=32000, max_rounds=60)
    passed, last = pytest_passes(WORKSPACE)
    files = sorted(p.name for p in WORKSPACE.glob("*.py")) if WORKSPACE.exists() else []
    toks = m["input_tokens"] or [0]
    return [{
        "scenario": "S6_marathon", "variant": "all_on", "completed": passed,
        "rounds": m["rounds"], "peak_input_tokens": max(toks), "final_input_tokens": toks[-1],
        "compactions": m["compactions"], **_timecols(m),
        "note": f"pytest: {last}; 产物={files}; tool_fails={m.get('tool_fails',0)}",
    }]


SCENARIOS = {
    "S1": s1_context, "S2": s2_retry, "S3": s3_resume,
    "S4": s4_tool_fail, "S5": s5_interrupt, "S6": s6_marathon,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="kimi")
    ap.add_argument("--only", nargs="*", default=list(SCENARIOS))
    args = ap.parse_args()

    # 让 agent 的 run_command 能用 venv 里的 python / pytest
    if VENV_BIN.exists():
        os.environ["PATH"] = f"{VENV_BIN}:{os.environ.get('PATH', '')}"
    load_env()
    RESULTS.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for key in args.only:
        print(f"\n{'='*70}\n运行场景 {key}（model={args.model}）\n{'='*70}")
        all_rows.extend(SCENARIOS[key](args.model))

    out = RESULTS / f"summary_{args.model}.csv"
    fields = ["scenario", "variant", "completed", "rounds", "peak_input_tokens",
              "final_input_tokens", "compactions", "wall_s", "api_s", "tool_s",
              "compact_s", "retry_s", "proj_2h_rounds", "note"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\n{'='*70}\n评测结果汇总（model={args.model}）→ {out}\n{'='*70}")
    for r in all_rows:
        print(f"  {r['scenario']:13s} {r['variant']:20s} done={str(r['completed']):5s} "
              f"rounds={r['rounds']:2d} wall={r['wall_s']:6.1f}s 2h≈{r['proj_2h_rounds']:4d}轮  {r['note']}")
    _clean()


if __name__ == "__main__":
    main()
