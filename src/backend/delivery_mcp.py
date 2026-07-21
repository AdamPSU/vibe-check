"""Read-only MCP adapter for the game package contract."""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .delivery import validate_delivery as validate_workspace


mcp = FastMCP(
    "delivery-validator",
    instructions="Validate the current game workspace before ending the maker session.",
)


@mcp.tool(
    name="validate_delivery",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def validate_delivery() -> dict[str, Any]:
    """Check that dist/ satisfies the daily-game delivery contract."""

    return validate_workspace(Path.cwd())


if __name__ == "__main__":
    mcp.run()
