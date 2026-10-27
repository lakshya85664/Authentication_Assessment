
"""Generate redacted evidence traces for Authentication Assessment."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from authentication.token_provider import FakeTokenProvider
from adapters.protected_service import ProtectedService
from authentication_assessment import dispatch


TRACE_DIR = PROJECT_ROOT / "traces"
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_scenario(name: str, role: str, *, service_fails: bool = False) -> dict:
    """Run one isolated scenario and record only redacted information."""
    provider = FakeTokenProvider(token_ttl_seconds=60)
    token = provider.issue_token(
        subject=f"evidence-{role}",
        roles=[role],
    )
    service = ProtectedService(fail=service_fails)

    call = {
        "name": "service_status_lookup",
        "arguments": {
            "request_id": f"EVIDENCE-{name.upper()}",
            "resource_id": "RESOURCE-REDACTED",
            "action": "read_status",
        },
    }

    try:
        result = dispatch(
            call,
            f"Bearer {token}",
            token_provider=provider,
            service=service,
        )
        status = result.get("status", "unknown")

        if status == "ok":
            outcome = "success"
        elif status in {"denied", "unauthorized"}:
            outcome = "denied"
        else:
            outcome = "failure"
        response = {
            "outcome": outcome,
            "authenticated": status in {"ok", "failed", "timeout", "rate_limited", "busy"},
            "status": status,
            "attempts": result.get("attempts"),
            "cache_hit": result.get("cache_hit"),
        }
        metrics = result.get("metrics", {})
        error_type = None
    except Exception as exc:
        outcome = "failure"
        response = {"outcome": "failure"}
        metrics = {}
        error_type = type(exc).__name__

    trace = {
        "event": name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "tool": "service_status_lookup",
        "principal": f"evidence-{role}",
        "credential": "[REDACTED]",
        "resource_id": "[REDACTED]",
        "outcome": outcome,
        "response": response,
        "error_type": error_type,
        "service_call_count": service.call_count,
        "metrics": metrics,
        "security_note": "Raw bearer token and sensitive resource identifiers are not recorded.",
    }
    write_json(TRACE_DIR / f"{name}.json", trace)
    return trace


def main() -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    scenarios = [
        run_scenario("success", "service_client"),
        run_scenario("access_denied", "unapproved_role"),
        run_scenario("provider_failure", "service_client", service_fails=True),
    ]

    summary = {
        "assessment": "Authentication Assessment",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_count": len(scenarios),
        "outcomes": {
            "success": sum(item["outcome"] == "success" for item in scenarios),
            "denied": sum(item["outcome"] == "denied" for item in scenarios),
            "failure": sum(item["outcome"] == "failure" for item in scenarios),
        },
        "trace_files": [f"traces/{item['event']}.json" for item in scenarios],
        "redaction": "Bearer tokens and resource identifiers are not included in raw form.",
    }
    write_json(OUTPUT_DIR / "evidence_summary.json", summary)

    print("Authentication Assessment — Evidence Generation")
    print("=" * 52)
    for item in scenarios:
        print(f"{item['event']}: {item['outcome']}")
    print(f"Summary: {OUTPUT_DIR / 'evidence_summary.json'}")
    print(f"Traces:  {TRACE_DIR}")


if __name__ == "__main__":
    main()
