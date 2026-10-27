
import time


class ProtectedService:
    """Fake protected service with controllable failure modes."""

    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        fail: bool = False,
    ):
        self.call_count = 0
        self.delay_seconds = delay_seconds
        self.fail = fail

    def get_status(
        self,
        resource_id: str,
        request_id: str,
    ) -> dict[str, str]:
        self.call_count += 1

        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        if self.fail:
            raise RuntimeError("simulated internal provider failure")

        return {
            "request_id": request_id,
            "resource_id": resource_id,
            "status": "active",
        }
