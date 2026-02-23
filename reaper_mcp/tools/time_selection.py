"""Time selection and loop tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import reapy
import reapy.reascript_api as RPR

from reaper_mcp.helpers import get_project, undo_block

mcp = FastMCP("time_selection")


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_time_selection() -> dict:
    """Get the current time selection range and loop/repeat state.

    Returns the time selection start and end in seconds, whether a time
    selection is active, and the current loop/repeat toggle state.
    """
    try:
        project = get_project()
        # GetSet_LoopTimeRange2 with isSet=False reads the current range.
        # Returns (start, end) after the project id and control booleans.
        result = RPR.GetSet_LoopTimeRange2(
            project.id,
            False,   # isSet: False = get (read)
            False,   # isLoop: False = time selection (not loop points)
            0.0,     # startOut
            0.0,     # endOut
            False,   # allowautoseek
        )
        # The return shape varies by binding; extract start/end from result
        if isinstance(result, tuple):
            start = result[2] if len(result) > 2 else result[0]
            end = result[3] if len(result) > 3 else result[1]
        else:
            start, end = 0.0, 0.0

        # Read loop/repeat state: -1 = query current
        repeat_state = RPR.GetSetRepeatEx(project.id, -1)

        has_selection = end > start

        return {
            "start": start,
            "end": end,
            "has_selection": has_selection,
            "length": end - start if has_selection else 0.0,
            "loop_enabled": bool(repeat_state),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get time selection: {exc}") from exc


# ---------------------------------------------------------------------------
# Time selection mutation
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_time_selection(
    start: Annotated[float, Field(description="Selection start in seconds", ge=0.0)],
    end: Annotated[float, Field(description="Selection end in seconds", ge=0.0)],
) -> dict:
    """Set the time selection range.

    To clear the time selection, pass start=0 and end=0.
    """
    if end < start:
        raise ToolError(
            f"Selection end ({end}) must be greater than or equal to start ({start})."
        )
    try:
        project = get_project()
        with undo_block("Set time selection"):
            RPR.GetSet_LoopTimeRange2(
                project.id,
                True,    # isSet: True = set (write)
                False,   # isLoop: False = time selection
                start,
                end,
                False,   # allowautoseek
            )
        return {
            "start": start,
            "end": end,
            "length": end - start,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set time selection: {exc}") from exc


# ---------------------------------------------------------------------------
# Loop control
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_loop(
    enabled: Annotated[bool, Field(description="True to enable looping, False to disable")],
    start: Annotated[
        float | None,
        Field(description="Loop start in seconds. Omit to leave loop points unchanged.", ge=0.0),
    ] = None,
    end: Annotated[
        float | None,
        Field(description="Loop end in seconds. Omit to leave loop points unchanged.", ge=0.0),
    ] = None,
) -> dict:
    """Enable or disable looping, and optionally set loop start/end points.

    If *start* and *end* are provided, the loop range is updated. Otherwise
    only the loop toggle is changed and the existing loop points are
    preserved.
    """
    if (start is None) != (end is None):
        raise ToolError(
            "Both 'start' and 'end' must be provided together, or both omitted."
        )
    if start is not None and end is not None and end <= start:
        raise ToolError(
            f"Loop end ({end}) must be greater than start ({start})."
        )
    try:
        project = get_project()
        with undo_block("Set loop"):
            # Set repeat/loop toggle
            RPR.GetSetRepeatEx(project.id, int(enabled))

            # Optionally update loop points
            if start is not None and end is not None:
                RPR.GetSet_LoopTimeRange2(
                    project.id,
                    True,    # isSet: True = set (write)
                    True,    # isLoop: True = loop points
                    start,
                    end,
                    False,   # allowautoseek
                )

        repeat_state = RPR.GetSetRepeatEx(project.id, -1)
        result: dict = {"loop_enabled": bool(repeat_state)}
        if start is not None and end is not None:
            result["loop_start"] = start
            result["loop_end"] = end
            result["loop_length"] = end - start
        return result
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set loop: {exc}") from exc
