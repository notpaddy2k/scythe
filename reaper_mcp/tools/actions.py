"""REAPER action execution — universal escape hatch for any REAPER command."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project

mcp = FastMCP("actions")


# ---------------------------------------------------------------------------
# Action tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def perform_action(
    action_id: Annotated[int, Field(description="Numeric REAPER action/command ID")],
) -> dict:
    """Execute a REAPER action by its numeric command ID.

    This is a universal escape hatch — any REAPER command can be triggered by
    its integer action ID. See the REAPER Actions dialog for available IDs.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        RPR.Main_OnCommand(action_id, 0)
        return {"action_id": action_id, "executed": True}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to perform action {action_id}: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def lookup_command_id(
    command_name: Annotated[
        str,
        Field(description="Named command identifier (e.g. '_SWS_ABOUT' or '_RS...')"),
    ],
) -> dict:
    """Look up the numeric command ID for a named REAPER action.

    Named commands typically start with an underscore (e.g. '_SWS_ABOUT').
    Returns the integer command ID that can be passed to perform_action.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        result = RPR.NamedCommandLookup(command_name)
        if result == 0:
            raise ToolError(
                f"Command not found: '{command_name}'. "
                f"Verify the name in REAPER's Actions dialog."
            )
        return {"command_name": command_name, "command_id": result}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to look up command '{command_name}': {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def perform_named_action(
    command_name: Annotated[
        str,
        Field(description="Named command identifier (e.g. '_SWS_ABOUT' or '_RS...')"),
    ],
) -> dict:
    """Look up a named action and execute it in one step.

    Combines lookup_command_id and perform_action for convenience. Named
    commands typically start with an underscore.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        cmd_id = RPR.NamedCommandLookup(command_name)
        if cmd_id == 0:
            raise ToolError(
                f"Command not found: '{command_name}'. "
                f"Verify the name in REAPER's Actions dialog."
            )
        RPR.Main_OnCommand(cmd_id, 0)
        return {
            "command_name": command_name,
            "command_id": cmd_id,
            "executed": True,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"Failed to perform named action '{command_name}': {exc}"
        ) from exc
