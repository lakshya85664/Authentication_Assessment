
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class AuthenticationInput(BaseModel):
    """Validated request for a protected service operation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: StrictStr = Field(min_length=1, max_length=64)
    resource_id: StrictStr = Field(min_length=1, max_length=64)
    action: Literal["read_status"] = "read_status"


class AuthenticationOutput(BaseModel):
    """Safe response returned by the protected service."""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: StrictStr
    resource_id: StrictStr
    status: Literal["active", "inactive", "unknown"]
    authenticated: bool


class ToolContract(BaseModel):
    """Metadata describing a tool and its execution requirements."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: StrictStr = Field(min_length=1, max_length=64)
    version: StrictStr = Field(min_length=1, max_length=16)
    description: StrictStr = Field(min_length=1, max_length=256)
    access: Literal["read", "write"]
    roles: list[StrictStr] = Field(min_length=1)
    input_schema: StrictStr
    output_schema: StrictStr
    requires_authentication: bool = True
    token_required: bool = True
    idempotent: bool = True
    retryable: bool = True
    max_attempts: int = Field(default=3, ge=1, le=5)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)


def build_authentication_contract() -> ToolContract:
    """Build the contract for the protected status lookup."""

    return ToolContract(
        name="service_status_lookup",
        version="1.0.0",
        description=(
            "Authenticate a service-to-service request and retrieve "
            "a protected resource status."
        ),
        access="read",
        roles=["service_client", "admin"],
        input_schema=AuthenticationInput.__name__,
        output_schema=AuthenticationOutput.__name__,
        requires_authentication=True,
        token_required=True,
        idempotent=True,
        retryable=True,
        max_attempts=3,
        timeout_seconds=5.0,
    )
