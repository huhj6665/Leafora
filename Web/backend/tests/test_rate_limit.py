"""进程内滑动窗口限流器单元测试（check 探测 / record 记录分离）."""
from app.services.rate_limit import InMemoryRateLimiter


def test_check_does_not_consume_quota():
    """探测不消耗额度：多次 check 后仍允许."""
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        assert limiter.check("k", 3, 60).allowed


def test_record_consumes_quota_and_blocks():
    """record 消耗额度：达到上限后 check 被拦截."""
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        limiter.record("k")
    result = limiter.check("k", 3, 60)
    assert not result.allowed
    assert result.retry_after > 0


def test_keys_isolated():
    """不同 key 互不影响."""
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        limiter.record("a")
    assert limiter.check("b", 3, 60).allowed


def test_reset_clears_state():
    """reset 清空所有记录."""
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        limiter.record("k")
    assert not limiter.check("k", 3, 60).allowed
    limiter.reset()
    assert limiter.check("k", 3, 60).allowed
