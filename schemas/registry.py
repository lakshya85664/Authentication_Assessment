
from schemas.tool_contract import (
    ToolContract,
    build_authentication_contract,
)


def build_registry() -> dict[str, ToolContract]:
    """Return the available tool contracts."""

    contract = build_authentication_contract()
    return {contract.name: contract}


def get_tool(
    name: str,
    registry: dict[str, ToolContract] | None = None,
) -> ToolContract | None:
    """Return a registered contract, or None for an unknown tool."""

    active_registry = registry if registry is not None else build_registry()
    return active_registry.get(name)
