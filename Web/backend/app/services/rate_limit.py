"""短信发送限流.

当前实现为进程内滑动窗口限流（开发阶段足够，无需引入 Redis）。
接口已抽象为 ``RateLimiter``，后续可在不改动业务代码的前提下替换为
Redis / 分布式限流实现。

关键设计：``check``（探测，不消耗额度）与 ``record``（记录一次成功事件）分离，
使业务层可以「先探测 → 发送 → 成功后记录」，从而避免发送失败仍消耗限流额度。

限流维度：
    - 单手机号：发送间隔 + 每日上限
    - 单 IP：    发送间隔 + 每日上限
"""
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass
class RateLimitResult:
    """限流判定结果."""

    allowed: bool
    retry_after: int = 0  # 秒；不被允许时建议等待时长


class RateLimiter(ABC):
    """限流器抽象接口."""

    @abstractmethod
    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        """探测指定 key 在窗口内是否已超限（不消耗额度）.

        参数:
            key:            限流维度标识（如手机号、IP）
            limit:          窗口内允许的最大次数
            window_seconds: 滑动窗口时长（秒）
        """
        raise NotImplementedError

    @abstractmethod
    def record(self, key: str) -> None:
        """记录一次成功事件（消耗额度）."""
        raise NotImplementedError


class InMemoryRateLimiter(RateLimiter):
    """进程内滑动窗口限流器（线程安全）."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            # 剔除窗口外的历史记录
            while events and now - events[0] >= window_seconds:
                events.popleft()
            if len(events) >= limit:
                oldest = events[0]
                retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
                return RateLimitResult(allowed=False, retry_after=retry_after)
            return RateLimitResult(allowed=True)

    def record(self, key: str) -> None:
        with self._lock:
            self._events[key].append(time.monotonic())

    def reset(self) -> None:
        """清空全部限流状态（测试隔离用）."""
        with self._lock:
            self._events.clear()


# 进程内默认限流器单例
rate_limiter = InMemoryRateLimiter()
