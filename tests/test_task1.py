
import pytest
from pydantic import ValidationError

from schemas.registry import build_registry, get_tool
from schemas.tool_contract import (
    AuthenticationInput,
    AuthenticationOutput,
    build_authentication_contract,
)


def test_contract_has_required_authentication_settings():
    contract = build_authentication_contract()

    assert contract.name == "service_status_lookup"
    assert contract.version == "1.0.0"
    assert contract.access == "read"
    assert contract.requires_authentication is True
    assert contract.token_required is True
    assert contract.idempotent is True
    assert contract.max_attempts == 3


def test_registry_registers_authentication_tool():
    registry = build_registry()

    assert "service_status_lookup" in registry
    assert get_tool("service_status_lookup", registry) == registry[
        "service_status_lookup"
    ]


def test_unknown_tool_is_not_registered():
    assert get_tool("unknown_tool") is None


def test_valid_input_is_accepted():
    request = AuthenticationInput(
        request_id="REQ-1601",
        resource_id="RESOURCE-1601",
    )

    assert request.action == "read_status"


def test_missing_request_id_is_rejected():
    with pytest.raises(ValidationError):
        AuthenticationInput(resource_id="RESOURCE-1601")


def test_extra_input_field_is_rejected():
    with pytest.raises(ValidationError):
        AuthenticationInput(
            request_id="REQ-1601",
            resource_id="RESOURCE-1601",
            token="should-not-be-an-input-field",
        )


def test_wrong_input_type_is_rejected():
    with pytest.raises(ValidationError):
        AuthenticationInput(
            request_id=123,
            resource_id="RESOURCE-1601",
        )


def test_valid_output_is_accepted():
    result = AuthenticationOutput(
        request_id="REQ-1601",
        resource_id="RESOURCE-1601",
        status="active",
        authenticated=True,
    )

    assert result.authenticated is True


def test_invalid_output_status_is_rejected():
    with pytest.raises(ValidationError):
        AuthenticationOutput(
            request_id="REQ-1601",
            resource_id="RESOURCE-1601",
            status="compromised",
            authenticated=True,
        )


def test_contract_rejects_excessive_attempt_limit():
    from schemas.tool_contract import ToolContract

    with pytest.raises(ValidationError):
        ToolContract(
            name="example",
            version="1.0.0",
            description="Example contract",
            access="read",
            roles=["service_client"],
            input_schema="Input",
            output_schema="Output",
            max_attempts=99,
        )