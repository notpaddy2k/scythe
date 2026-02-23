"""REAPER extended state (persistent key-value storage)."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project

mcp = FastMCP("ext_state")


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Section = Annotated[str, Field(description="ExtState section name")]
Key = Annotated[str, Field(description="ExtState key within the section")]


# ---------------------------------------------------------------------------
# Extended state tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_ext_state(
    section: Section,
    key: Key,
) -> dict:
    """Read a value from REAPER's extended state store.

    Extended state is a key-value system organised by section. Returns an
    empty string if the key does not exist.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        result = RPR.GetExtState(section, key)
        return {"section": section, "key": key, "value": result}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"Failed to get ext state [{section}][{key}]: {exc}"
        ) from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_ext_state(
    section: Section,
    key: Key,
    value: Annotated[str, Field(description="Value to store")],
    persist: Annotated[
        bool,
        Field(description="If True (default), value is saved across REAPER sessions"),
    ] = True,
) -> dict:
    """Write a value to REAPER's extended state store.

    When persist is True the value survives REAPER restarts (stored in
    reaper-extstate.ini). Set persist to False for session-only data.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        RPR.SetExtState(section, key, value, persist)
        return {
            "section": section,
            "key": key,
            "value": value,
            "persist": persist,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"Failed to set ext state [{section}][{key}]: {exc}"
        ) from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_ext_state(
    section: Section,
    key: Key,
) -> dict:
    """Delete a key from REAPER's extended state store.

    Removes the key from both the in-memory state and the persisted ini file.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        RPR.DeleteExtState(section, key, True)
        return {"section": section, "key": key, "deleted": True}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"Failed to delete ext state [{section}][{key}]: {exc}"
        ) from exc
