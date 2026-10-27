
from authentication.token_provider import FakeTokenProvider


class AuthenticationError(Exception):
    """Raised when a service token is invalid or expired."""


def authenticate_bearer_token(
    authorization_header: str | None,
    provider: FakeTokenProvider,
) -> dict:
    """Validate a Bearer token and return its authenticated identity."""

    if not isinstance(authorization_header, str):
        raise AuthenticationError("Missing bearer token")

    scheme, separator, token = authorization_header.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token
        or " " in token
    ):
        raise AuthenticationError("Malformed bearer token")

    identity = provider.validate_token(token)

    if identity is None:
        raise AuthenticationError("Invalid or expired bearer token")

    return identity
