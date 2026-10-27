
from adapters.protected_service import ProtectedService
from authentication.token_provider import FakeTokenProvider
from authentication_assessment import dispatch


def make_call():
    return {
        "name": "service_status_lookup",
        "arguments": {
            "request_id": "REQ-1603",
            "resource_id": "RESOURCE-1603",
        },
    }


def setup_auth():
    provider = FakeTokenProvider()
    token = provider.issue_token(
        "inventory-service",
        ["service_client"],
    )
    return provider, f"Bearer {token}"


def test_malformed_arguments_are_rejected():
    provider, header = setup_auth()
    service = ProtectedService()
    call = make_call()
    call["arguments"]["unexpected"] = "not allowed"

    result = dispatch(
        call, header, token_provider=provider, service=service
    )

    assert result["status"] == "invalid"
    assert service.call_count == 0


def test_wrong_argument_type_is_rejected():
    provider, header = setup_auth()
    service = ProtectedService()
    call = make_call()
    call["arguments"]["request_id"] = 123

    result = dispatch(
        call, header, token_provider=provider, service=service
    )

    assert result["status"] == "invalid"
    assert service.call_count == 0


def test_provider_failure_is_sanitized():
    provider, header = setup_auth()
    service = ProtectedService(fail=True)

    result = dispatch(
        make_call(), header, token_provider=provider, service=service
    )

    assert result["status"] == "failed"
    assert "simulated internal provider failure" not in str(result)
    assert service.call_count == 1


def test_provider_timeout_returns_controlled_response():
    provider, header = setup_auth()
    service = ProtectedService(delay_seconds=0.2)

    result = dispatch(
        make_call(),
        header,
        token_provider=provider,
        service=service,
        timeout_seconds=0.01,
    )

    assert result["status"] == "timeout"
    assert result["events"][0]["event"] == "provider.timeout"


def test_invalid_timeout_is_rejected_before_execution():
    provider, header = setup_auth()
    service = ProtectedService()

    result = dispatch(
        make_call(),
        header,
        token_provider=provider,
        service=service,
        timeout_seconds=0,
    )

    assert result["status"] == "invalid"
    assert service.call_count == 0


def test_invalid_authentication_still_has_no_side_effect():
    provider = FakeTokenProvider()
    service = ProtectedService()

    result = dispatch(
        make_call(),
        "Bearer definitely-invalid",
        token_provider=provider,
        service=service,
    )

    assert result["status"] == "unauthorized"
    assert service.call_count == 0


def test_provider_response_is_validated():
    class MalformedService:
        call_count = 0

        def get_status(self, resource_id, request_id):
            self.call_count += 1
            return {
                "request_id": request_id,
                "resource_id": resource_id,
                "status": "secret_internal_state",
            }

    provider, header = setup_auth()
    service = MalformedService()

    result = dispatch(
        make_call(), header, token_provider=provider, service=service
    )

    assert result["status"] == "failed"
    assert result["events"][0]["event"] == "provider.response_invalid"


def test_non_dictionary_request_is_rejected():
    provider, header = setup_auth()
    service = ProtectedService()

    result = dispatch(
        None, header, token_provider=provider, service=service
    )

    assert result["status"] == "invalid"
    assert service.call_count == 0
