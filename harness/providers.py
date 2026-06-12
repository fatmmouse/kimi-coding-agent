"""Provider 抽象层：屏蔽两种 wire 协议，对上层只露一个 chat() 接口。

为什么需要这一层：
  - Kimi For Coding 走 **Anthropic Messages 协议**（system 抽顶层、tool_result 进 user turn、强制 thinking）
  - DeepSeek 走 **OpenAI Chat Completions 协议**（扁平 messages、tool 角色）
上层主循环不该关心这些差异。所以内部统一用 OpenAI 风格 messages（扁平、好存 JSONL、人类可读），
两个 adapter 各自负责往返翻译。这正是 Kimi CLI 用 kosong 包做的事——把 provider 差异关在一个盒子里。

统一内部 message 形状（OpenAI 风格）：
  {"role": "system",    "content": str}
  {"role": "user",      "content": str}
  {"role": "assistant", "content": str|None, "tool_calls": [{"id","type":"function","function":{"name","arguments":json_str}}]}
  {"role": "tool",      "tool_call_id": str, "content": str}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


# ---------- 统一返回类型 ----------
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    total: int = 0


@dataclass
class LLMResponse:
    assistant_msg: dict          # OpenAI 风格 assistant 消息，直接 append 进 history
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""
    usage: Usage = field(default_factory=Usage)


# ---------- .env 读取（key 不进代码、不进 git） ----------
def load_env(path: str = ".env") -> None:
    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


# 中性工具 schema（provider 各自转成自己协议的形状），由 tools.py 提供
# 形状：{"name", "description", "parameters": <json schema>}


class Provider:
    """所有 provider 的接口。"""

    name: str = ""
    model: str = ""
    context_window: int = 128_000

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        raise NotImplementedError


# ---------- DeepSeek：OpenAI 协议，几乎零翻译 ----------
class DeepSeekProvider(Provider):
    name = "deepseek"
    context_window = 128_000

    def __init__(self, model: str = "deepseek-v4-pro"):
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )

    def _to_openai_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._to_openai_tools(tools) if tools else None,
        )
        msg = resp.choices[0].message
        assistant_msg = msg.model_dump(exclude_none=True)
        tool_calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {"__raw__": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        u = resp.usage
        usage = Usage(
            input=u.prompt_tokens, output=u.completion_tokens, total=u.total_tokens
        )
        return LLMResponse(
            assistant_msg=assistant_msg,
            tool_calls=tool_calls,
            text=msg.content or "",
            usage=usage,
        )


# ---------- Kimi For Coding：Anthropic 协议，需要双向翻译 ----------
class KimiProvider(Provider):
    name = "kimi"
    context_window = 262_144

    def __init__(self, model: str = "kimi-for-coding", max_tokens: int = 8192):
        import anthropic

        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=os.environ["KIMI_API_KEY"],
            base_url="https://api.kimi.com/coding",
            # Kimi For Coding 只对 coding agent 开放，需冒充 Claude Code 的 UA
            default_headers={"user-agent": "claude-cli/1.0.88 (external)"},
        )

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]

    def _to_anthropic_messages(self, messages: list[dict]):
        """OpenAI 风格 → Anthropic 风格。返回 (system_str, anthropic_messages)。

        关键转换：
        - system 抽到顶层参数
        - assistant.tool_calls → tool_use content block
        - role=tool 消息 → tool_result block，且必须并进相邻的 user turn（Anthropic 要求）
        """
        system_parts: list[str] = []
        out: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                system_parts.append(m.get("content") or "")
            elif role == "user":
                out.append({"role": "user", "content": m.get("content") or ""})
            elif role == "assistant":
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    fn = tc["function"]
                    try:
                        args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    blocks.append(
                        {"type": "tool_use", "id": tc["id"], "name": fn["name"], "input": args}
                    )
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            elif role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": m["tool_call_id"],
                    "content": m.get("content") or "",
                }
                # 并进上一个 user turn，否则新建一个
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return "\n\n".join(p for p in system_parts if p), out

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        system, amsgs = self._to_anthropic_messages(messages)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system or None,
            messages=amsgs,
            tools=self._to_anthropic_tools(tools) if tools else [],
        )
        # Anthropic response → OpenAI 风格 assistant 消息
        text = ""
        tool_calls: list[ToolCall] = []
        oa_tool_calls: list[dict] = []
        for block in resp.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input or {}))
                oa_tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {"name": block.name, "arguments": json.dumps(block.input or {}, ensure_ascii=False)},
                    }
                )
        assistant_msg: dict = {"role": "assistant", "content": text or None}
        if oa_tool_calls:
            assistant_msg["tool_calls"] = oa_tool_calls
        u = resp.usage
        usage = Usage(
            input=u.input_tokens + getattr(u, "cache_read_input_tokens", 0),
            output=u.output_tokens,
            total=u.input_tokens + u.output_tokens,
        )
        return LLMResponse(
            assistant_msg=assistant_msg, tool_calls=tool_calls, text=text, usage=usage
        )


def make_provider(name: str) -> Provider:
    name = name.lower()
    if name in ("kimi", "k2", "k2.6"):
        return KimiProvider()
    if name in ("deepseek", "ds"):
        return DeepSeekProvider()
    raise ValueError(f"unknown provider: {name}（可选 kimi / deepseek）")
