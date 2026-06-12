"""机制④ 用户中断 —— 安全点模型 + 危险命令审批门。

第一性原理：2 小时的自主运行里，用户一定会想插话——「方向错了，改成 X」「先停一下」。
如果中断只能靠 kill 进程，用户要么干等两小时，要么丢掉全部进度。所以中断必须是
一等公民操作，而且要满足两个性质：

  1. 安全点（borrow 自 Kimi CLI 的 shield 思想）：中断只在「工具调用边界」生效，
     不会打断一次正在进行的文件写入或状态落盘。任何时刻停下，磁盘状态都是自洽的。
  2. 中断是上下文（borrow 自 Claude Code）：用户打断不是悄悄丢弃，而是作为一条 user
     消息注入对话——模型恢复时看得见「我在做 X 时被要求改成 Y」，能据此改向而非懵掉。

两种中断：
  - steering（软）：运行中用户敲入一行字 → 进队列，在下个安全点作为 user 消息注入，agent 改向继续。
  - Ctrl-C（硬）：第一次 = 优雅停（落盘 + 打印 resume 命令）；第二次 = 强退（append-only 已保证不丢）。

外加危险命令审批门（borrow 自 Claude Code permission）：run_command 命中危险模式时暂停等确认。
"""

from __future__ import annotations

import queue
import re
import sys
import threading

# 危险命令模式：命中则需用户确认
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf?\b",
    r"\bgit\s+push\b",
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/",
    r"\bchmod\s+-R\b",
    r":\(\)\s*\{",  # fork bomb
]


def is_dangerous(cmd: str) -> bool:
    return any(re.search(p, cmd) for p in DANGEROUS_PATTERNS)


class StdinSteering:
    """后台线程非阻塞读 stdin。运行中用户输入的整行进队列，主循环在安全点取走。

    只在交互式 TTY 下启动；评测/管道环境自动禁用（避免抢占 stdin）。
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and sys.stdin is not None and sys.stdin.isatty()
        self._q: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        try:
            for line in sys.stdin:
                if self._stop.is_set():
                    break
                line = line.strip()
                if line:
                    self._q.put(line)
        except Exception:
            pass

    def drain(self) -> list[str]:
        """安全点调用：取走目前排队的所有 steering 消息。"""
        out = []
        while not self._q.empty():
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def stop(self):
        self._stop.set()
