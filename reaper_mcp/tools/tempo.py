"""Tempo and time signature tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import reapy
import reapy.reascript_api as RPR

from reaper_mcp.helpers import get_project, undo_block

mcp = FastMCP("tempo")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

TempoMarkerIndex = Annotated[int, Field(description="Zero-based tempo marker index", ge=0)]
BPM = Annotated[float, Field(description="Beats per minute", gt=0.0)]
Position = Annotated[float, Field(description="Position in seconds", ge=0.0)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_tempo_marker(project_id, index: int) -> dict:
    """Read a single tempo/time-signature marker and return a summary dict."""
    result = RPR.GetTempoTimeSigMarker(
        project_id, index, 0.0, 0, 0, 0.0, 0, 0, False
    )
    # Returns: (retval, proj, ptidx, timepos, measurepos, beatpos,
    #           bpm, timesig_num, timesig_denom, lineartempo)
    _, _, timepos, measurepos, beatpos, bpm, ts_num, ts_denom, linear = (
        result[0],   # retval
        result[1],   # proj (discarded — same as input)
        result[2],   # timepos
        result[3],   # measurepos
        result[4],   # beatpos
        result[5],   # bpm
        result[6],   # timesig_num
        result[7],   # timesig_denom
        result[8],   # lineartempo
    )
    return {
        "index": index,
        "position": timepos,
        "bpm": bpm,
        "time_sig_num": ts_num,
        "time_sig_denom": ts_denom,
        "linear_tempo": bool(linear),
    }


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_tempo_info() -> dict:
    """Get the current master tempo and all tempo/time-signature markers.

    Returns the current BPM, the total number of tempo markers, and a list
    of marker details (position, BPM, time signature, linear tempo flag).
    """
    try:
        project = get_project()
        current_bpm = RPR.Master_GetTempo()
        n_markers = RPR.CountTempoTimeSigMarkers(project.id)
        markers = [
            _read_tempo_marker(project.id, i)
            for i in range(n_markers)
        ]
        return {
            "current_bpm": current_bpm,
            "n_tempo_markers": n_markers,
            "tempo_markers": markers,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get tempo info: {exc}") from exc


# ---------------------------------------------------------------------------
# Tempo marker mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_tempo_marker(
    position: Position,
    bpm: BPM,
    time_sig_num: Annotated[
        int,
        Field(description="Time signature numerator (e.g. 4 for 4/4). 0 to keep project default."),
    ] = 0,
    time_sig_denom: Annotated[
        int,
        Field(description="Time signature denominator (e.g. 4 for 4/4). 0 to keep project default."),
    ] = 0,
) -> dict:
    """Add a new tempo marker at the specified position.

    Optionally set a new time signature at that point. Pass 0 for numerator
    and denominator to inherit the current project time signature.
    """
    try:
        project = get_project()
        with undo_block("Add tempo marker"):
            ok = RPR.SetTempoTimeSigMarker(
                project.id,
                -1,             # ptidx: -1 = create new
                position,
                -1,             # measurepos: -1 = auto
                -1,             # beatpos: -1 = auto
                bpm,
                time_sig_num,
                time_sig_denom,
                False,          # lineartempo
            )
        if not ok:
            raise ToolError("REAPER refused to create the tempo marker.")
        # Read back the count to confirm
        n_markers = RPR.CountTempoTimeSigMarkers(project.id)
        return {
            "position": position,
            "bpm": bpm,
            "time_sig_num": time_sig_num,
            "time_sig_denom": time_sig_denom,
            "n_tempo_markers": n_markers,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add tempo marker: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def edit_tempo_marker(
    marker_index: TempoMarkerIndex,
    bpm: Annotated[
        float | None,
        Field(description="New BPM value. Omit to leave unchanged.", gt=0.0),
    ] = None,
    time_sig_num: Annotated[
        int | None,
        Field(description="New time signature numerator. Omit to leave unchanged."),
    ] = None,
    time_sig_denom: Annotated[
        int | None,
        Field(description="New time signature denominator. Omit to leave unchanged."),
    ] = None,
) -> dict:
    """Edit an existing tempo marker's BPM and/or time signature.

    Only the provided values are changed; omitted parameters keep their
    current values.
    """
    if bpm is None and time_sig_num is None and time_sig_denom is None:
        raise ToolError(
            "At least one of 'bpm', 'time_sig_num', or 'time_sig_denom' "
            "must be provided."
        )
    try:
        project = get_project()
        n_markers = RPR.CountTempoTimeSigMarkers(project.id)
        if marker_index < 0 or marker_index >= n_markers:
            raise ToolError(
                f"Tempo marker index {marker_index} out of range. "
                f"Project has {n_markers} tempo marker(s) (valid: 0-{n_markers - 1})."
            )

        # Read existing values
        existing = _read_tempo_marker(project.id, marker_index)

        new_bpm = bpm if bpm is not None else existing["bpm"]
        new_num = time_sig_num if time_sig_num is not None else existing["time_sig_num"]
        new_denom = time_sig_denom if time_sig_denom is not None else existing["time_sig_denom"]

        with undo_block("Edit tempo marker"):
            ok = RPR.SetTempoTimeSigMarker(
                project.id,
                marker_index,
                existing["position"],
                -1,             # measurepos: -1 = auto
                -1,             # beatpos: -1 = auto
                new_bpm,
                new_num,
                new_denom,
                existing["linear_tempo"],
            )
        if not ok:
            raise ToolError(
                f"REAPER refused to update tempo marker at index {marker_index}."
            )
        return _read_tempo_marker(project.id, marker_index)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to edit tempo marker: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_tempo_marker(
    marker_index: TempoMarkerIndex,
) -> dict:
    """Delete a tempo/time-signature marker by its index.

    WARNING: This permanently removes the tempo marker.
    """
    try:
        project = get_project()
        n_markers = RPR.CountTempoTimeSigMarkers(project.id)
        if marker_index < 0 or marker_index >= n_markers:
            raise ToolError(
                f"Tempo marker index {marker_index} out of range. "
                f"Project has {n_markers} tempo marker(s) (valid: 0-{n_markers - 1})."
            )
        with undo_block("Delete tempo marker"):
            ok = RPR.DeleteTempoTimeSigMarker(project.id, marker_index)
        if not ok:
            raise ToolError(
                f"REAPER refused to delete tempo marker at index {marker_index}."
            )
        return {
            "deleted_index": marker_index,
            "n_tempo_markers": RPR.CountTempoTimeSigMarkers(project.id),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete tempo marker: {exc}") from exc
