"""四个工具 + 中性 schema。工具被钉死在 workspace 内，run_command 带超时。

设计原则（借鉴各家共识）：
  - 工具异常**永不**冒泡到主循环。任何失败都转成一段错误文本作为 tool result 回喂模型，让它自纠。
  - 工具结果进上下文前由 context 层截断；这里只负责产出完整结果。
  - run_command 必须有超时，否则一条挂住的命令能拖死整个 2 小时任务。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

WORKSPACE = Path("./workspace").resolve()
COMMAND_TIMEOUT = 120  # 秒；单条命令最长执行时间


def _safe_path(path: str) -> Path:
    p = (WORKSPACE / path).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError(f"path escapes workspace: {path}")
    return p


def read_file(path: str) -> str:
    return _safe_path(path).read_text()


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} chars to {path}"


def edit_file(path: str, old: str, new: str) -> str:
    """精确替换：old 必须在文件中唯一出现一次，否则报错让模型重读。"""
    p = _safe_path(path)
    text = p.read_text()
    n = text.count(old)
    if n == 0:
        raise ValueError(f"old string not found in {path}")
    if n > 1:
        raise ValueError(f"old string appears {n} times in {path}; make it unique")
    p.write_text(text.replace(old, new))
    return f"edited {path}"


def run_command(cmd: str) -> str:
    """在 workspace 里跑一条 shell 命令，超时即杀。返回退出码 + stdout + stderr。"""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=WORKSPACE, capture_output=True, text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"exit=TIMEOUT\n命令超过 {COMMAND_TIMEOUT}s 被强制终止：{cmd}"
    return f"exit={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"


TOOL_FUNCS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "run_command": run_command,
}

# 中性 schema：provider 层各自转成 OpenAI / Anthropic 形状
TOOLS = [
    {
        "name": "read_file",
        "description": "读取 workspace 里一个文本文件的内容。",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对 workspace 的路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "把内容写入 workspace 里的文件（整体覆盖）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对 workspace 的路径"},
                "content": {"type": "string", "description": "要写入的完整内容"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "精确替换文件中一段唯一出现的文本。适合小改动，避免重写整文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "相对 workspace 的路径"},
                "old": {"type": "string", "description": "要被替换的原文本（须在文件中唯一）"},
                "new": {"type": "string", "description": "替换后的新文本"},
            },
            "required": ["path", "old", "new"],
        },
    },
    {
        "name": "run_command",
        "description": f"在 workspace 下执行一条 shell 命令（超时 {COMMAND_TIMEOUT}s），返回退出码和输出。",
        "parameters": {
            "type": "object",
            "properties": {"cmd": {"type": "string", "description": "要执行的 shell 命令"}},
            "required": ["cmd"],
        },
    },
]
