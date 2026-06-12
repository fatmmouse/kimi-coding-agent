"""机制③ 工具调用 / API 失败恢复 —— 分类处置，绝不让单点失败拖垮 2 小时任务。

第一性原理：在 2 小时里，瞬时故障是统计必然——网络抖动、429 限流、5xx、命令超时。
如果每个瞬时故障都让进程退出，任务永远跑不完。但也不能无脑重试：参数错了重试一万次还是错。
所以要**分类**：

  API 层（在 with_retry 里）：
    - 429 / 5xx / 超时 / 连接错  → 可恢复，指数退避 + jitter 重试（参数借鉴 Codex：200ms×2^n，jitter 0.9-1.1）
    - 4xx 参数错（400/401/404）  → 不可恢复，直接抛，重试无意义
    - 上下文溢出（context overflow）→ 由主循环在重试前先做一次紧急压缩

  工具层（在主循环里）：
    - 工具抛任何异常 → 捕获，把错误文本作为 tool result 回喂模型，让它自纠。绝不冒泡。

  防呆（LoopGuard）：
    - 相同工具 + 相同参数连续重复 N 次 → 判定死循环，注入纠正提示
    - 连续失败 M 次 → 熔断，暂停并落盘求助
"""

from __future__ import annotations

import random
import time

# 退避参数（借鉴 Codex util.rs）
INITIAL_DELAY = 0.2
BACKOFF_FACTOR = 2.0
MAX_RETRIES = 5

# 防呆阈值
LOOP_REPEAT_LIMIT = 3      # 同样的调用连续出现几次算死循环
CONSEC_FAILURE_LIMIT = 5   # 连续工具失败几次熔断


class ContextOverflow(Exception):
    """上下文超窗专用信号，让主循环知道该先压缩再重试。"""


def _is_retryable(err: Exception) -> bool:
    status = getattr(err, "status_code", None)
    if status is not None:
        if status == 429 or status >= 500:
            return True
        if 400 <= status < 500:
            return False
    name = type(err).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "apiconnection", "internalserver"))


def _is_overflow(err: Exception) -> bool:
    msg = str(err).lower()
    return any(k in msg for k in ("context", "too long", "maximum context", "token", "length"))


def with_retry(fn, *, enabled: bool = True, on_attempt=None):
    """带分类重试地执行 fn()。enabled=False 时只跑一次（用于 ablation 对照）。

    返回 fn() 的结果；不可恢复错误或重试耗尽则抛出。上下文溢出抛 ContextOverflow。
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except Exception as err:  # noqa: BLE001 —— 这层就是要兜住所有 API 异常
            if _is_overflow(err) and getattr(err, "status_code", None) not in (429,):
                raise ContextOverflow(str(err)) from err
            if not enabled or not _is_retryable(err) or attempt > MAX_RETRIES:
                raise
            delay = INITIAL_DELAY * (BACKOFF_FACTOR ** (attempt - 1))
            delay *= random.uniform(0.9, 1.1)
            if on_attempt:
                on_attempt(attempt, delay, err)
            time.sleep(delay)


class LoopGuard:
    """检测死循环（同调用反复）和连续失败熔断。"""

    def __init__(self):
        self._last_sig = None
        self._repeat = 0
        self._consec_fail = 0

    def check_repeat(self, tool_name: str, args: dict) -> str | None:
        sig = (tool_name, repr(sorted(args.items())) if isinstance(args, dict) else repr(args))
        if sig == self._last_sig:
            self._repeat += 1
        else:
            self._last_sig = sig
            self._repeat = 1
        if self._repeat >= LOOP_REPEAT_LIMIT:
            self._repeat = 0  # 提示后清零，给模型机会改
            return (
                f"[死循环检测] 你已连续 {LOOP_REPEAT_LIMIT} 次用相同参数调用 {tool_name}，"
                f"结果没有变化。换个方法，或检查前面的输出再决定下一步。"
            )
        return None

    def record_tool_outcome(self, ok: bool) -> str | None:
        if ok:
            self._consec_fail = 0
            return None
        self._consec_fail += 1
        if self._consec_fail >= CONSEC_FAILURE_LIMIT:
            return (
                f"[熔断] 连续 {CONSEC_FAILURE_LIMIT} 次工具调用失败。停下来重新评估："
                f"是不是方向错了？把当前困境写进 todo.md，换一条路。"
            )
        return None
