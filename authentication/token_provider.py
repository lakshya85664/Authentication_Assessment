
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time


@dataclass(frozen=True)
class TokenRecord:
    """Internal token metadata. Never serialize the secret token."""

    subject: str
    roles: tuple[str, ...]
    expires_at: float
    token_digest: str


class FakeTokenProvider:
    """
    Assessment-only credential provider.

    Issues opaque random bearer tokens and stores only their digests.
    This is a test double, not a production identity provider.
    """

    def __init__(self, token_ttl_seconds: float = 60.0):
        if token_ttl_seconds <= 0:
            raise ValueError("Token lifetime must be positive")

        self.token_ttl_seconds = token_ttl_seconds
        self._records: dict[str, TokenRecord] = {}

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue_token(
        self,
        subject: str,
        roles: list[str],
    ) -> str:
        if not subject.strip():
            raise ValueError("Subject must not be empty")
        if not roles or any(not role.strip() for role in roles):
            raise ValueError("At least one valid role is required")

        token = secrets.token_urlsafe(32)
        digest = self._digest(token)

        self._records[digest] = TokenRecord(
            subject=subject,
            roles=tuple(roles),
            expires_at=time.monotonic() + self.token_ttl_seconds,
            token_digest=digest,
        )
        return token

    def validate_token(self, token: str) -> dict | None:
        """
        Return a safe identity snapshot for a valid token.
        Return None for invalid or expired tokens.
        """
        if not isinstance(token, str) or not token:
            return None

        digest = self._digest(token)
        record = self._records.get(digest)

        if record is None:
            return None

        # Compare digests in constant time.
        if not hmac.compare_digest(record.token_digest, digest):
            return None

        if time.monotonic() >= record.expires_at:
            self._records.pop(digest, None)
            return None

        return {
            "subject": record.subject,
            "roles": list(record.roles),
            "expires_at": record.expires_at,
        }
