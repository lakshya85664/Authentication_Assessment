# Authentication Assessment

## Project Overview

This project implements a protected tool-calling workflow with bearer-token authentication, role-based authorization, strict request validation, and reliability controls. It demonstrates how a tool registry and contract can define permitted operations and how an authenticated service-to-service request can access a protected resource.

## Objectives

- Define a validated tool contract and registry.
- Issue and validate short-lived bearer tokens.
- Enforce role-based authorization.
- Validate request arguments and handle failures safely.
- Implement bounded retries, timeouts, rate limiting, concurrency control, and caching.
- Generate redacted JSON evidence and an operator report.

## Architecture

1. **Tool Registry:** identifies the available tool and its contract.
2. **Input Validation:** validates request fields using Pydantic models.
3. **Authentication:** validates bearer tokens through a fake credential provider.
4. **Authorization:** checks whether the authenticated principal has an allowed role.
5. **Reliability Controller:** coordinates execution limits, caching, and metrics.
6. **Protected Service:** simulates a service-to-service operation.
7. **Evidence Generation:** writes redacted traces and an evidence summary.

## Technology Stack

- Python
- Pydantic
- Pytest
- Standard-library concurrency and time utilities
- JSON-based evidence and structured traces

## Project Structure

```text
Authentication_Assessment/
├── adapters/
├── authentication/
├── reliability/
├── schemas/
├── tests/
├── traces/
├── outputs/
│   ├── evidence_summary.json
│   └── generate_evidence.py
├── reports/
│   └── operator_report.md
├── authentication_assessment.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Setup

Open Command Prompt in the project directory and activate the existing virtual environment:

```cmd
.venv\Scripts\activate
```

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

## Run the Tests

```cmd
python -m pytest -q
```

Latest verified result: **40 passed in 0.26 seconds**.

## Generate Evidence

```cmd
python outputs\generate_evidence.py
```

The generator creates three scenario traces:

- `traces/success.json` — successful authenticated request.
- `traces/access_denied.json` — unauthorized role denied access.
- `traces/provider_failure.json` — authenticated request with a simulated provider failure.

The summary is written to `outputs/evidence_summary.json`, and the operator report is available at `reports/operator_report.md`.

## Security Notes

The token provider is a simulated assessment component, not a production identity service. The project redacts bearer credentials and resource identifiers from its generated evidence. Production use would require a real identity provider, secure transport, secret management, appropriate key rotation, and operational security monitoring.

## Reflection

This assessment helped me understand that authentication, authorization, and reliable execution are distinct responsibilities within a tool-calling system. A valid token establishes the caller's identity, while role-based authorization determines whether the caller is permitted to use a particular tool. Strict validation and sanitized error responses help keep malformed requests and internal failures from exposing implementation details.

The implementation also demonstrated the value of bounded retries, timeouts, rate limiting, concurrency controls, and caching. These mechanisms address different operational risks and should be configured according to the tool's behavior and the consequences of repeated execution.

During evidence generation, I found that the evidence collector must follow the actual response contract. A successful service call was initially classified incorrectly because the collector checked a field at the wrong level. Inspecting the generated traces and correcting the classification logic resolved the issue without changing the dispatcher, and the full test suite continued to pass.

The next improvements would be broader evidence for expired tokens, malformed authorization headers, timeout handling, and transient-failure recovery. For production deployment, I would replace the fake credential provider with a secure identity integration and add centralized monitoring, key management, and audit retention.
