
from dataclasses import dataclass, field
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryableError(Exception):
    """An error that may be retried for a safe operation."""


class PermanentError(Exception):
    """An error that must not be retried."""


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    sleep_fn: Callable[[float], None] = time.sleep
    attempt_log: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.base_delay_seconds < 0:
            raise ValueError("base delay cannot be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max delay must be >= base delay")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff multiplier must be >= 1")

    def run(
        self,
        operation: Callable[[], T],
        *,
        retryable: bool = True,
    ) -> T:
        self.attempt_log.clear()

        for attempt in range(1, self.max_attempts + 1):
            try:
                result = operation()
                self.attempt_log.append({
                    "attempt": attempt,
                    "outcome": "success",
                })
                return result
            except Exception as exc:
                transient = isinstance(exc, RetryableError)
                self.attempt_log.append({
                    "attempt": attempt,
                    "outcome": "failure",
                    "error_type": type(exc).__name__,
                    "transient": transient,
                })

                if (
                    not retryable
                    or isinstance(exc, PermanentError)
                    or not transient
                    or attempt >= self.max_attempts
                ):
                    raise

                delay = min(
                    self.base_delay_seconds
                    * self.backoff_multiplier ** (attempt - 1),
                    self.max_delay_seconds,
                )
                self.sleep_fn(delay)

        raise RuntimeError("Retry loop ended unexpectedly")
