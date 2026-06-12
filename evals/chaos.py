"""故障注入 —— 把恢复能力变成可复现实验，而不是「写了就算」。

思路直接借鉴 Kimi CLI 官方自带的 ChaosChatProvider：用一个 wrapper 包住真实 provider，
按概率（带 seed 可复现）把 chat() 调用变成一次 API 故障。这样机制③的价值可以被量化测出来：
同一任务、同一 seed，retry on 完成、retry off 崩溃。
"""

from __future__ import annotations

import random


class FakeAPIError(Exception):
    """模拟可恢复的 API 故障（带 status_code，让 recovery 层识别）。"""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"injected API error {status_code}")


class ChaosProvider:
    """代理真实 provider，按概率在 chat() 前注入故障。"""

    def __init__(self, inner, error_probability=0.0, error_types=None, fail_first_n=0, seed=None):
        self.inner = inner
        self.error_probability = error_probability
        self.error_types = error_types or [429, 500, 502, 503]
        self.fail_first_n = fail_first_n      # 前 N 次调用必失败（确定性，便于精确断言）
        self._rng = random.Random(seed)
        self._calls = 0

    # 透传真实 provider 的属性
    @property
    def model(self):
        return self.inner.model

    @property
    def context_window(self):
        return self.inner.context_window

    def chat(self, messages, tools):
        self._calls += 1
        if self._calls <= self.fail_first_n:
            raise FakeAPIError(self._rng.choice(self.error_types))
        if self.error_probability > 0 and self._rng.random() < self.error_probability:
            raise FakeAPIError(self._rng.choice(self.error_types))
        return self.inner.chat(messages, tools)
