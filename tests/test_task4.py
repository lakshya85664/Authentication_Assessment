
import pytest

from authentication_assessment import dispatch
from authentication.token_provider import FakeTokenProvider
from adapters.protected_service import ProtectedService
from reliability.retry_policy import (
    RetryPolicy,
    RetryableError,
    PermanentError,
)
from reliability.controls import (
    SlidingWindowRateLimiter,
    ReliabilityController,
)



def make_request(request_id="req-401", resource_id="resource-1"):
    return {
        "name": "service_status_lookup",
        "arguments": {
            "request_id": request_id,
            "resource_id": resource_id,
            "action": "read_status",
        },
    }



def make_auth():
    provider = FakeTokenProvider()
    token = provider.issue_token("test-service", ["service_client"])
    return provider, f"Bearer {token}"


def test_retry_policy_recovers_after_transient_failure():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RetryableError("temporary failure")
        return "recovered"

    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0,
        max_delay_seconds=0,
        sleep_fn=lambda _: None,
    )

    assert policy.run(operation) == "recovered"
    assert calls["count"] == 3
    assert len(policy.attempt_log) == 3
    assert policy.attempt_log[-1]["outcome"] == "success"


def test_retry_policy_stops_at_attempt_limit():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise RetryableError("still failing")

    policy = RetryPolicy(
        max_attempts=2,
        base_delay_seconds=0,
        max_delay_seconds=0,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(RetryableError):
        policy.run(operation)

    assert calls["count"] == 2
    assert len(policy.attempt_log) == 2


def test_permanent_error_is_not_retried():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise PermanentError("not recoverable")

    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0,
        max_delay_seconds=0,
        sleep_fn=lambda _: None,
    )

    with pytest.raises(PermanentError):
        policy.run(operation)

    assert calls["count"] == 1


def test_retry_policy_rejects_invalid_attempt_limit():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=10)


def test_rate_limiter_rejects_requests_over_limit():
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False


def test_rate_limiter_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=0)

    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(window_seconds=0)


def test_reliability_controller_caches_successful_results():
    controller = ReliabilityController(rate_limit=10)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        return {"status": "active"}

    first, first_hit = controller.execute("same-key", operation)
    second, second_hit = controller.execute("same-key", operation)

    assert first == second == {"status": "active"}
    assert first_hit is False
    assert second_hit is True
    assert calls["count"] == 1
    assert controller.metrics.snapshot()["cache_hits"] == 1


def test_reliability_controller_does_not_cache_failures():
    controller = ReliabilityController(rate_limit=10)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise ValueError("failure")

    with pytest.raises(ValueError):
        controller.execute("failed-key", operation)

    with pytest.raises(ValueError):
        controller.execute("failed-key", operation)

    assert calls["count"] == 2


def test_dispatch_returns_success_and_metrics():
    provider, header = make_auth()
    service = ProtectedService()
    controller = ReliabilityController(rate_limit=10)
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0,
        max_delay_seconds=0,
        sleep_fn=lambda _: None,
    )

    result = dispatch(
        make_request(),
        header,
        token_provider=provider,
        service=service,
        retry_policy=policy,
        reliability=controller,
    )

    print("DEBUG DISPATCH RESULT:", result)
    assert result["status"] == "ok"
    assert result["data"]["authenticated"] is True
    assert result["cache_hit"] is False
    assert result["metrics"]["succeeded"] == 1


def test_dispatch_uses_idempotency_cache():
    provider, header = make_auth()
    service = ProtectedService()
    controller = ReliabilityController(rate_limit=10)

    first = dispatch(
        make_request(),
        header,
        token_provider=provider,
        service=service,
        reliability=controller,
    )
    second = dispatch(
        make_request(),
        header,
        token_provider=provider,
        service=service,
        reliability=controller,
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["cache_hit"] is True
    assert service.call_count == 1
    assert second["metrics"]["cache_hits"] == 1


def test_dispatch_reports_rate_limit():
    provider, header = make_auth()
    service = ProtectedService()
    controller = ReliabilityController(rate_limit=1)

    first = dispatch(
        make_request("req-1"),
        header,
        token_provider=provider,
        service=service,
        reliability=controller,
    )
    second = dispatch(
        make_request("req-2"),
        header,
        token_provider=provider,
        service=service,
        reliability=controller,
    )

    assert first["status"] == "ok"
    assert second["status"] == "rate_limited"
    assert second["metrics"]["rate_limited"] == 1


def test_dispatch_records_retries_in_metrics():
    provider, header = make_auth()
    controller = ReliabilityController(rate_limit=10)

    class FlakyService(ProtectedService):
        def get_status(self, resource_id, request_id):
            self.call_count += 1

            if self.call_count == 1:
                raise RetryableError("temporary service failure")

            return {
                "request_id": request_id,
                "resource_id": resource_id,
                "status": "active",
            }

    service = FlakyService()
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0,
        max_delay_seconds=0,
        sleep_fn=lambda _: None,
    )

    result = dispatch(
        make_request("req-retry", "resource-retry"),
        header,
        token_provider=provider,
        service=service,
        retry_policy=policy,
        reliability=controller,
    )

    assert result["status"] == "ok"
    assert service.call_count == 2
    assert result["metrics"]["retries"] == 1
    assert len(result["attempts"]) == 2

