
import time

from adapters.protected_service import ProtectedService
from authentication.token_provider import FakeTokenProvider
from authentication_assessment import dispatch


def make_call():
    return {
        "name": "service_status_lookup",
        "arguments": {
            "request_id": "REQ-1602",
            "resource_id": "RESOURCE-1602",
        },
    }


def run_dispatch(token, provider, service, role="service_client"):
    return dispatch(
        make_call(),
        f"Bearer {token}" if token is not None else None,
        token_provider=provider,
        service=service,
    )


def test_valid_token_allows_protected_call():
    provider = FakeTokenProvider()
    token = provider.issue_token("inventory-service", ["service_client"])
    service = ProtectedService()

    result = run_dispatch(token, provider, service)

    assert result["status"] == "ok"
    assert result["data"]["authenticated"] is True
    assert service.call_count == 1


def test_invalid_token_is_rejected_without_side_effect():
    provider = FakeTokenProvider()
    service = ProtectedService()

    result = run_dispatch("invalid-token", provider, service)

    assert result["status"] == "unauthorized"
    assert service.call_count == 0


def test_missing_token_is_rejected_without_side_effect():
    provider = FakeTokenProvider()
    service = ProtectedService()

    result = run_dispatch(None, provider, service)

    assert result["status"] == "unauthorized"
    assert service.call_count == 0


def test_expired_token_is_rejected_without_side_effect():
    provider = FakeTokenProvider(token_ttl_seconds=0.01)
    token = provider.issue_token("inventory-service", ["service_client"])
    service = ProtectedService()

    time.sleep(0.03)
    result = run_dispatch(token, provider, service)

    assert result["status"] == "unauthorized"
    assert service.call_count == 0


def test_wrong_role_is_denied_without_side_effect():
    provider = FakeTokenProvider()
    token = provider.issue_token("reporting-service", ["report_viewer"])
    service = ProtectedService()

    result = run_dispatch(token, provider, service)

    assert result["status"] == "denied"
    assert service.call_count == 0


def test_malformed_bearer_header_is_rejected():
    provider = FakeTokenProvider()
    service = ProtectedService()

    result = dispatch(
        make_call(),
        "Basic abc123",
        token_provider=provider,
        service=service,
    )

    assert result["status"] == "unauthorized"
    assert service.call_count == 0


def test_unknown_tool_is_rejected_before_service_call():
    provider = FakeTokenProvider()
    token = provider.issue_token("inventory-service", ["service_client"])
    service = ProtectedService()
    call = make_call()
    call["name"] = "unregistered_tool"

    result = dispatch(
        call,
        f"Bearer {token}",
        token_provider=provider,
        service=service,
    )

    assert result["status"] == "denied"
    assert service.call_count == 0


def test_token_is_not_in_success_response():
    provider = FakeTokenProvider()
    token = provider.issue_token("inventory-service", ["service_client"])
    service = ProtectedService()

    result = run_dispatch(token, provider, service)

    assert token not in str(result)


def test_provider_does_not_store_raw_token():
    provider = FakeTokenProvider()
    token = provider.issue_token("inventory-service", ["service_client"])

    assert token not in provider._records
    assert len(provider._records) == 1


def test_provider_rejects_nonpositive_token_lifetime():
    try:
        FakeTokenProvider(token_ttl_seconds=0)
        assert False, "Expected ValueError"
    except ValueError:
        pass
