
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from pydantic import ValidationError

from adapters.protected_service import ProtectedService
from authentication.auth_policy import (
    AuthenticationError,
    authenticate_bearer_token,
)
from authentication.token_provider import FakeTokenProvider
from reliability.controls import ReliabilityController
from reliability.retry_policy import RetryPolicy
from schemas.registry import get_tool
from schemas.tool_contract import (
    AuthenticationInput,
    AuthenticationOutput,
)


def dispatch(
    call: dict[str, Any],
    authorization_header: str | None,
    *,
    token_provider: FakeTokenProvider,
    service: ProtectedService,
    timeout_seconds: float = 5.0,
    retry_policy: RetryPolicy | None = None,
    reliability: ReliabilityController | None = None,
) -> dict[str, Any]:
    """Validate, authenticate, authorize, and reliably execute a tool call."""

    # 1. Validate the outer request.
    if not isinstance(call, dict):
        return {
            "status": "invalid",
            "error": "Invalid tool request",
            "next_action": "correct_arguments",
            "events": [{"event": "request.validation_failed"}],
        }

    # The registered tool name is provided under "name".
    name = call.get("name")
    contract = get_tool(name) if isinstance(name, str) else None

    if contract is None:
        return {
            "status": "denied",
            "error": "Unknown tool",
            "next_action": "choose_registered_tool",
            "events": [{"event": "tool.unknown"}],
        }

    # 2. Validate the tool arguments against the input schema.
    try:
        request = AuthenticationInput.model_validate(
            call.get("arguments", {})
        )
    except (ValidationError, AttributeError, TypeError):
        return {
            "status": "invalid",
            "error": "Invalid request arguments",
            "next_action": "correct_arguments",
            "events": [{"event": "request.validation_failed"}],
        }

    # 3. Authenticate the bearer token.
    try:
        identity = authenticate_bearer_token(
            authorization_header,
            token_provider,
        )
    except AuthenticationError:
        return {
            "status": "unauthorized",
            "error": "Authentication failed",
            "next_action": "obtain_valid_token",
            "events": [{"event": "authentication.denied"}],
        }

    # 4. Authorize the authenticated principal.
    if not set(identity["roles"]).intersection(contract.roles):
        return {
            "status": "denied",
            "error": "Authorization denied",
            "next_action": "request_authorization",
            "events": [{"event": "authorization.denied"}],
        }

    # 5. Validate timeout configuration.
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        return {
            "status": "invalid",
            "error": "Invalid timeout configuration",
            "next_action": "review_configuration",
            "events": [{"event": "configuration.invalid"}],
        }

    controller = reliability or ReliabilityController()
    policy = retry_policy or RetryPolicy(
        max_attempts=contract.max_attempts,
    )

    # 6. Build an idempotency key using the authenticated subject.
    # Never include the raw bearer token in the cache key.
    cache_key = (
        f"{identity['subject']}:{request.request_id}:"
        f"{request.resource_id}:{request.action}"
    )

    # 7. Execute the protected service with a timeout.
    def operation():
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            service.get_status,
            request.resource_id,
            request.request_id,
        )

        try:
            return future.result(
                timeout=min(
                    timeout_seconds,
                    contract.timeout_seconds,
                )
            )
        except TimeoutError:
            future.cancel()
            raise
        finally:
            executor.shutdown(
                wait=False,
                cancel_futures=True,
            )

    # 8. Apply retries and record additional attempts as retries.
    def run_with_retry_metrics():
        try:
            return policy.run(
                operation,
                retryable=(
                    contract.retryable and contract.idempotent
                ),
            )
        finally:
            # N attempts means N - 1 retries.
            # RetryPolicy.run resets its attempt log at the start
            # of each execution.
            retry_count = max(
                0,
                len(policy.attempt_log) - 1,
            )

            if retry_count:
                controller.metrics.increment(
                    "retries",
                    retry_count,
                )

    # 9. Apply rate limiting, concurrency limits, and result caching.
    try:
        service_result, cache_hit = controller.execute(
            cache_key,
            run_with_retry_metrics,
        )

    except TimeoutError:
        controller.metrics.increment("timed_out")

        return {
            "status": "timeout",
            "error": "Protected service timed out",
            "next_action": "retry_or_review",
            "events": [{"event": "provider.timeout"}],
            "attempts": list(policy.attempt_log),
            "metrics": controller.metrics.snapshot(),
        }

    except RuntimeError as exc:
        message = str(exc)

        if message == "Rate limit exceeded":
            event = "reliability.rate_limited"
            status = "rate_limited"
        elif message == "Concurrency limit exceeded":
            event = "reliability.busy"
            status = "busy"
        else:
            event = "provider.failed"
            status = "failed"

        return {
            "status": status,
            "error": (
                message
                if status in {"rate_limited", "busy"}
                else "Protected service failed"
            ),
            "next_action": "retry_or_review",
            "events": [{"event": event}],
            "attempts": list(policy.attempt_log),
            "metrics": controller.metrics.snapshot(),
        }

    except Exception:
        return {
            "status": "failed",
            "error": "Protected service failed",
            "next_action": "review_request",
            "events": [{"event": "provider.failed"}],
            "attempts": list(policy.attempt_log),
            "metrics": controller.metrics.snapshot(),
        }

    # 10. Validate the protected service response before returning it.
    try:
        output = AuthenticationOutput(
            request_id=service_result["request_id"],
            resource_id=service_result["resource_id"],
            status=service_result["status"],
            authenticated=True,
        )
    except (ValidationError, KeyError, TypeError):
        return {
            "status": "failed",
            "error": "Invalid protected service response",
            "next_action": "review_provider",
            "events": [{"event": "provider.response_invalid"}],
            "metrics": controller.metrics.snapshot(),
        }

    # 11. Return a validated, sanitized response and observability data.
    return {
        "status": "ok",
        "data": output.model_dump(),
        "next_action": "return_result",
        "events": [
            {
                "event": (
                    "idempotency.cache_hit"
                    if cache_hit
                    else "tool.completed"
                )
            }
        ],
        "attempts": (
            []
            if cache_hit
            else list(policy.attempt_log)
        ),
        "cache_hit": cache_hit,
        "metrics": controller.metrics.snapshot(),
    }


if __name__ == "__main__":
    import json

    provider = FakeTokenProvider(token_ttl_seconds=60)
    token = provider.issue_token(
        subject="inventory-service",
        roles=["service_client"],
    )

    result = dispatch(
        {
            "name": "service_status_lookup",
            "arguments": {
                "request_id": "REQ-1601",
                "resource_id": "RESOURCE-1601",
            },
        },
        f"Bearer {token}",
        token_provider=provider,
        service=ProtectedService(),
    )

    print(json.dumps(result, indent=2))
