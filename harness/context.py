"""机制① 上下文管理 —— 三层防线，对抗「2 小时必然撑爆窗口」。

第一性原理：一个 2 小时任务可能产生几百轮工具调用，每轮的工具输出（命令日志、文件内容）
动辄上千 token。线性堆进 messages，输入侧 token 会单调暴涨，最终撞上下文窗口 → 报错或截断 → 任务崩。
所以上下文不能放任增长，必须主动治理。三层：

  防线一·工具结果截断（offload）：单条工具结果超阈值就截头尾留中间标记，完整结果落盘到
    .agent/outputs/，并告诉模型「完整内容在 <path>，需要可 read_file」。借鉴 Claude Code 40k 截断。
  防线二·历史压缩（compaction）：当输入 token ≥ 窗口 * 触发比例，调一次 LLM 把旧历史压成
    结构化摘要（当前任务/已完成/错误与解法/关键文件/下一步），替换被压缩的部分，保留最近 N 轮完整 turn。
    借鉴 Kimi CLI compact.md 的优先级 + 双条件触发。
  防线三·文件系统即记忆：真正重要的状态（todo.md、计划、产物）本就在 workspace 文件里，
    不靠对话记忆。压缩丢掉的是过程，不是结果。

切割铁律（借鉴 pi）：压缩切点只能落在完整 turn 边界，绝不能把一个 assistant 的 tool_calls
和它对应的 tool 结果切散——切散直接造成 provider 400。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

OUTPUTS_DIR = Path(".agent/outputs")

# ---- 防线一参数 ----
TOOL_RESULT_LIMIT = 4000   # 单条工具结果进上下文的字符上限
HEAD_KEEP = 2000
TAIL_KEEP = 1500

# ---- 防线二参数 ----
TRIGGER_RATIO = 0.75       # 输入 token 占窗口比例达到此值触发压缩（窗口留足余量）
KEEP_RECENT_TURNS = 3      # 压缩后保留最近 N 个完整 turn


def estimate_tokens(messages: list[dict]) -> int:
    """字符数/4 粗估。会被下一次真实 usage 校正，仅用于触发判断。"""
    chars = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            chars += len(c)
        for tc in m.get("tool_calls") or []:
            chars += len(json.dumps(tc.get("function", {}), ensure_ascii=False))
    return chars // 4


# ---------- 防线一：工具结果截断 + 落盘 ----------
def offload_tool_result(result: str, tool_name: str) -> str:
    if len(result) <= TOOL_RESULT_LIMIT:
        return result
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{tool_name}-{int(time.time()*1000)}.txt"
    fpath = OUTPUTS_DIR / fname
    fpath.write_text(result, encoding="utf-8")
    head = result[:HEAD_KEEP]
    tail = result[-TAIL_KEEP:]
    omitted = len(result) - HEAD_KEEP - TAIL_KEEP
    return (
        f"{head}\n\n"
        f"... [截断 {omitted} 字符；完整结果已存到 {fpath}，需要时用 read_file 读它] ...\n\n"
        f"{tail}"
    )


# ---------- 防线二：历史压缩 ----------
COMPACTION_PROMPT = """你在压缩一个 coding agent 的对话历史。按下列优先级提炼，丢掉冗余，输出结构化摘要：

优先级（高到低）：
1. 当前正在做什么（RIGHT NOW）
2. 遇到的错误及其解法
3. 代码/文件的最终状态（只留最终版，丢掉中间尝试）
4. 环境与项目结构
5. 关键设计决定及理由
6. 未完成的 TODO

用以下结构输出（缺项写「无」）：
<current_focus>当前焦点</current_focus>
<completed>已完成的事，每条一行</completed>
<errors_fixed>错误: 解法</errors_fixed>
<files>涉及的文件: 一句话作用</files>
<decisions>关键决定: 理由</decisions>
<todo>未完成项</todo>"""


def find_compaction_cut(messages: list[dict], keep_recent_turns: int) -> int:
    """从尾部往前数 keep_recent_turns 个 user/assistant turn，返回切点 index。
    切点之前的被压缩，之后的（含切点）原样保留。保证不切散 tool_calls/tool 结果。"""
    # 跳过开头的 system 消息
    start = 0
    while start < len(messages) and messages[start]["role"] == "system":
        start += 1

    turn_starts = [
        i for i in range(start, len(messages)) if messages[i]["role"] in ("user", "assistant")
    ]
    if len(turn_starts) <= keep_recent_turns:
        return -1  # 历史太短，不值得压
    cut = turn_starts[-keep_recent_turns]
    return cut


def compact(messages: list[dict], provider, keep_recent_turns: int = KEEP_RECENT_TURNS):
    """把切点之前的历史压成一条摘要消息。返回 (new_messages, usage) 或 (None, None) 表示没压。

    切点之前若有 system 消息予以保留（稳定前缀，利于 KV cache）。
    """
    cut = find_compaction_cut(messages, keep_recent_turns)
    if cut < 0:
        return None, None

    system_msgs = [m for m in messages[:cut] if m["role"] == "system"]
    to_compress = [m for m in messages[:cut] if m["role"] != "system"]
    to_preserve = messages[cut:]

    transcript = []
    for m in to_compress:
        role = m["role"]
        content = m.get("content") or ""
        if m.get("tool_calls"):
            calls = ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
            content = (content + f" [调用工具: {calls}]").strip()
        transcript.append(f"{role}: {content}")
    joined = "\n".join(transcript)

    resp = provider.chat(
        [
            {"role": "system", "content": COMPACTION_PROMPT},
            {"role": "user", "content": f"以下是要压缩的历史：\n\n{joined}"},
        ],
        tools=[],
    )
    summary_msg = {
        "role": "user",
        "content": f"[先前 {len(to_compress)} 条历史已压缩，摘要如下]\n\n{resp.text}",
    }
    new_messages = system_msgs + [summary_msg] + to_preserve
    return new_messages, resp.usage
