"""Envelope and automation tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project, validate_track_index, undo_block

mcp = FastMCP("envelopes")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

TrackIndex = Annotated[int, Field(description="Zero-based track index", ge=0)]
EnvelopeIndex = Annotated[int, Field(description="Zero-based envelope index on the track", ge=0)]
EnvelopeShape = Annotated[
    int,
    Field(
        description=(
            "Point shape: 0=linear, 1=square, 2=slow start/end, "
            "3=fast start, 4=fast end, 5=bezier"
        ),
        ge=0,
        le=5,
    ),
]
AutomationMode = Annotated[
    int,
    Field(
        description="Automation mode: 0=trim/off, 1=read, 2=touch, 3=write, 4=latch",
        ge=0,
        le=4,
    ),
]

# ---------------------------------------------------------------------------
# Shape label lookup (for readable output)
# ---------------------------------------------------------------------------

_SHAPE_NAMES = {
    0: "linear",
    1: "square",
    2: "slow start/end",
    3: "fast start",
    4: "fast end",
    5: "bezier",
}

_AUTOMATION_MODE_NAMES = {
    0: "trim/off",
    1: "read",
    2: "touch",
    3: "write",
    4: "latch",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_envelope_index(track, envelope_index: int):
    """Return the envelope ID at *envelope_index* on *track*, or raise ToolError."""
    import reapy.reascript_api as RPR

    n = RPR.CountTrackEnvelopes(track.id)
    if envelope_index < 0 or envelope_index >= n:
        raise ToolError(
            f"Envelope index {envelope_index} out of range on track '{track.name}'. "
            f"Track has {n} envelope{'s' if n != 1 else ''} "
            f"(valid: 0-{n - 1})."
        )
    return RPR.GetTrackEnvelope(track.id, envelope_index)


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_track_envelopes(
    track_index: TrackIndex,
) -> dict:
    """List all envelopes on a track.

    Returns each envelope's index, name, point count, and internal
    envelope ID.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)

        n_envelopes = RPR.CountTrackEnvelopes(track.id)
        envelopes = []
        for i in range(n_envelopes):
            env_id = RPR.GetTrackEnvelope(track.id, i)
            _, _, buf, _ = RPR.GetEnvelopeName(env_id, "", 256)
            n_points = RPR.CountEnvelopePoints(env_id)
            envelopes.append({
                "index": i,
                "name": buf,
                "n_points": n_points,
                "envelope_id": str(env_id),
            })
        return {"n_envelopes": n_envelopes, "envelopes": envelopes}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list track envelopes: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_envelope_points(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
) -> dict:
    """Get all points on a track envelope.

    Returns each point's index, time, value, shape, tension, and
    selected state. Shape values: 0=linear, 1=square, 2=slow start/end,
    3=fast start, 4=fast end, 5=bezier.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        n_points = RPR.CountEnvelopePoints(env_id)
        points = []
        for i in range(n_points):
            (
                _retval, _env_id, _pt_idx,
                time, value, shape, tension, selected,
            ) = RPR.GetEnvelopePoint(env_id, i)
            points.append({
                "index": i,
                "time": time,
                "value": value,
                "shape": shape,
                "shape_name": _SHAPE_NAMES.get(shape, "unknown"),
                "tension": tension,
                "selected": selected,
            })
        return {"n_points": n_points, "points": points}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get envelope points: {exc}") from exc


# ---------------------------------------------------------------------------
# Envelope point mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_envelope_point(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
    time: Annotated[float, Field(description="Time position in seconds", ge=0.0)],
    value: Annotated[float, Field(description="Envelope value (range depends on envelope type)")],
    shape: EnvelopeShape = 0,
    tension: Annotated[float, Field(description="Tension for bezier curves (-1.0 to 1.0)", ge=-1.0, le=1.0)] = 0.0,
) -> dict:
    """Add a point to a track envelope.

    The point is inserted and the envelope is sorted afterwards.
    Shape values: 0=linear, 1=square, 2=slow start/end, 3=fast start,
    4=fast end, 5=bezier.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        with undo_block("Add envelope point"):
            RPR.InsertEnvelopePoint(
                env_id, time, value, shape, tension,
                False,  # selected
                True,   # noSort — we sort manually after
            )
            RPR.Envelope_SortPoints(env_id)
        return {
            "time": time,
            "value": value,
            "shape": shape,
            "shape_name": _SHAPE_NAMES.get(shape, "unknown"),
            "tension": tension,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add envelope point: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_envelope_points(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
    time_start: Annotated[float, Field(description="Start of the time range in seconds", ge=0.0)],
    time_end: Annotated[float, Field(description="End of the time range in seconds", gt=0.0)],
) -> dict:
    """Delete all envelope points within a time range.

    WARNING: All points between time_start and time_end (exclusive) will
    be permanently removed.
    """
    try:
        import reapy.reascript_api as RPR

        if time_end <= time_start:
            raise ToolError(
                f"time_end ({time_end}) must be greater than time_start ({time_start})."
            )

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        with undo_block("Delete envelope points"):
            RPR.DeleteEnvelopePointRange(env_id, time_start, time_end)
        return {
            "time_start": time_start,
            "time_end": time_end,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete envelope points: {exc}") from exc


# ---------------------------------------------------------------------------
# Automation mode
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_automation_mode(
    track_index: TrackIndex,
    mode: AutomationMode,
) -> dict:
    """Set the automation mode for a track.

    Modes: 0=trim/off, 1=read, 2=touch, 3=write, 4=latch.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)

        with undo_block("Set track automation mode"):
            RPR.SetTrackAutomationMode(track.id, mode)
        return {
            "track_index": track_index,
            "mode": mode,
            "mode_name": _AUTOMATION_MODE_NAMES.get(mode, "unknown"),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track automation mode: {exc}") from exc


# ---------------------------------------------------------------------------
# Automation items
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_automation_item(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
    position: Annotated[float, Field(description="Start position in seconds", ge=0.0)],
    length: Annotated[float, Field(description="Length of the automation item in seconds", gt=0.0)],
) -> dict:
    """Add an automation item to a track envelope.

    Creates a new automation item (not pooled) at the given position
    and length. Returns the index of the newly created automation item.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        with undo_block("Add automation item"):
            auto_item_index = RPR.InsertAutomationItem(
                env_id,
                -1,        # pool_id: -1 for new (not pooled)
                position,
                length,
            )
        return {
            "automation_item_index": auto_item_index,
            "position": position,
            "length": length,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add automation item: {exc}") from exc
