
from collections import deque
from threading import Lock, Semaphore
import time
from typing import Any, Callable


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: float = 60.0):
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Invalid rate-limit configuration")
        self.limit = limit
        self.window_seconds = window_seconds
        self._events = deque()
        self._lock = Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while (
                self._events
                and now - self._events[0] >= self.window_seconds
            ):
                self._events.popleft()

            if len(self._events) >= self.limit:
                return False

            self._events.append(now)
            return True


class ExecutionMetrics:
    def __init__(self):
        self._values = {
            "started": 0,
            "succeeded": 0,
            "failed": 0,
            "retries": 0,
            "rate_limited": 0,
            "cache_hits": 0,
            "timed_out": 0,
        }
        self._lock = Lock()

    def increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            if key not in self._values:
                raise KeyError(f"Unknown metric: {key}")
            self._values[key] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


class ReliabilityController:
    """Applies rate limiting, concurrency limits, and successful-result caching."""

    def __init__(
        self,
        *,
        rate_limit: int = 10,
        window_seconds: float = 60.0,
        max_concurrent: int = 4,
    ):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be positive")

        self.limiter = SlidingWindowRateLimiter(
            rate_limit,
            window_seconds,
        )
        self._semaphore = Semaphore(max_concurrent)
        self._cache: dict[str, Any] = {}
        self._cache_lock = Lock()
        self.metrics = ExecutionMetrics()

    def execute(
        self,
        key: str,
        operation: Callable[[], Any],
    ) -> tuple[Any, bool]:
        with self._cache_lock:
            if key in self._cache:
                self.metrics.increment("cache_hits")
                return self._cache[key], True

        if not self.limiter.allow():
            self.metrics.increment("rate_limited")
            raise RuntimeError("Rate limit exceeded")

        acquired = self._semaphore.acquire(blocking=False)
        if not acquired:
            raise RuntimeError("Concurrency limit exceeded")

        self.metrics.increment("started")
        try:
            result = operation()
            with self._cache_lock:
                self._cache[key] = result
            self.metrics.increment("succeeded")
            return result, False
        except Exception:
            self.metrics.increment("failed")
            raise
        finally:
            self._semaphore.release()
