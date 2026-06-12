"""机制② 任务状态记录 —— 物理层 + 语义层。

为什么 2 小时任务必须有它：进程会崩、机器会被关、API 会断。如果状态只活在内存里，
一次崩溃就抹掉两小时的工作。所以状态必须在每个事件发生的瞬间就落到磁盘。

两层设计（借鉴 Codex rollout + Claude Code todo）：
  - 物理层 SessionLog：append-only JSONL，每个事件（user/assistant/tool_result/compaction…）
    即时写盘并 flush。这是会话的**唯一权威记录**，崩溃后从它逐行重放重建 messages。
    人类可读，jq 即可审计。
  - 语义层 todo.md：模型自己维护的 `- [ ]` / `- [x]` 清单，写在 workspace 里。
    它不受上下文压缩影响（在文件系统里），resume 后模型靠它一眼看出做到哪了。

resume 的本质：不是「重跑」，是「重放 JSONL 把 messages 拼回来，从断点继续」。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

SESSIONS_DIR = Path(".agent/sessions")


class SessionLog:
    def __init__(self, session_id: str, resume: bool = False):
        self.session_id = session_id
        self.dir = SESSIONS_DIR / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        # 'a' 模式：resume 时续写不覆盖；新会话时文件不存在自动创建
        self._fh = self.path.open("a", encoding="utf-8")

    def append(self, kind: str, payload: dict) -> None:
        """写一条事件并立即 flush + fsync —— 崩溃也不丢这一行。"""
        rec = {"ts": time.time(), "kind": kind, **payload}
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()
        import os
        os.fsync(self._fh.fileno())

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    # ---------- resume：重放 JSONL 重建 messages ----------
    @classmethod
    def replay(cls, session_id: str) -> tuple[list[dict], dict]:
        """读 events.jsonl，把 message 类事件拼回 OpenAI 风格 messages。
        返回 (messages, meta)。meta 含 task / model / 已完成轮数。"""
        path = SESSIONS_DIR / session_id / "events.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"no session: {session_id}")
        messages: list[dict] = []
        meta: dict = {"rounds": 0}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            kind = rec.get("kind")
            if kind == "meta":
                meta.update(rec.get("data", {}))
            elif kind == "message":
                messages.append(rec["message"])
            elif kind == "round":
                meta["rounds"] = rec.get("n", meta["rounds"])
            elif kind == "compaction":
                # 压缩事件：用压缩后的 messages 整体替换历史
                messages = list(rec["messages"])
        return messages, meta


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")
