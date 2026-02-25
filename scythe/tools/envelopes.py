"""Envelope and automation tools."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from scythe.helpers import get_project, validate_track_index, validate_fx_index, undo_block

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
FxIndex = Annotated[int, Field(description="Zero-based FX slot index", ge=0)]
ParamIndex = Annotated[int, Field(description="Zero-based FX parameter index", ge=0)]

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


def _edit_envelope_chunk(env_id, *, active: bool | None = None,
                         visible: bool | None = None,
                         default_shape: int | None = None) -> str:
    """Read an envelope's state chunk, apply edits, write it back.

    Returns the modified chunk string.  Regex patterns use line-start
    anchors (``(?m)^``) to avoid matching substrings like LVIS or
    VOLENV2_ACT.
    """
    import reapy.reascript_api as RPR

    ret = RPR.GetEnvelopeStateChunk(env_id, "", 65536, False)
    # reapy returns a list [retval, env_id, chunk_str, buf_sz, isUndo]
    if isinstance(ret, (list, tuple)):
        chunk = ret[2] if len(ret) >= 3 else ret[0]
    else:
        chunk = str(ret)

    if not chunk:
        raise ToolError("Failed to read envelope state chunk.")

    if active is not None:
        val = "1" if active else "0"
        chunk = re.sub(r'(?m)^(ACT )\d', rf'\g<1>{val}', chunk)

    if visible is not None:
        val = "1" if visible else "0"
        chunk = re.sub(r'(?m)^(VIS )\d', rf'\g<1>{val}', chunk)

    if default_shape is not None:
        if re.search(r'(?m)^DEFSHAPE ', chunk):
            chunk = re.sub(
                r'(?m)^(DEFSHAPE )\d+',
                rf'\g<1>{default_shape}',
                chunk,
            )
        else:
            # Insert DEFSHAPE before the closing >
            chunk = chunk.rstrip().rstrip('>').rstrip()
            chunk += f'\nDEFSHAPE {default_shape}\n>'

    RPR.SetEnvelopeStateChunk(env_id, chunk, False)
    return chunk


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
            ret = RPR.GetEnvelopePoint(env_id, i, 0.0, 0.0, 0, 0.0, False)
            # ret: [retval, env_id, pt_idx, time, value, shape, tension, selected]
            time = ret[3]
            value = ret[4]
            shape = ret[5]
            tension = ret[6]
            selected = ret[7]
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
                True,   # noSort -- we sort manually after
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
# FX envelope creation & management
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def create_fx_envelope(
    track_index: TrackIndex,
    fx_index: FxIndex,
    param_index: ParamIndex,
    activate: Annotated[bool, Field(description="Activate the envelope after creation")] = True,
    default_shape: EnvelopeShape = 1,
) -> dict:
    """Create an automation envelope for an FX parameter.

    Returns the envelope name, point count, and its index in the
    track's envelope list.  If the envelope already exists it is
    returned as-is (no duplicate is created).
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)

        if param_index < 0 or param_index >= fx.n_params:
            raise ToolError(
                f"Parameter index {param_index} out of range. "
                f"FX '{fx.name}' has {fx.n_params} parameters "
                f"(valid: 0-{fx.n_params - 1})."
            )

        # Get param name for readable output
        try:
            param_name = fx.params[param_index].name
        except Exception:
            _, _, _, param_name, _ = RPR.TrackFX_GetParamName(
                track.id, fx_index, param_index, "", 256
            )

        with undo_block(
            f"Create FX envelope for '{param_name}' on '{fx.name}' "
            f"(track '{track.name}')"
        ):
            env_id = RPR.GetFXEnvelope(track.id, fx_index, param_index, True)

            if not env_id:
                raise ToolError(
                    f"Failed to create envelope for parameter '{param_name}' "
                    f"on FX '{fx.name}'."
                )

            # Activate and configure via chunk editing
            if activate or default_shape != 0:
                _edit_envelope_chunk(
                    env_id,
                    active=activate,
                    visible=True if activate else None,
                    default_shape=default_shape,
                )

        # Find this envelope's index in the track's envelope list
        envelope_index = -1
        n_envelopes = RPR.CountTrackEnvelopes(track.id)
        for i in range(n_envelopes):
            check_env = RPR.GetTrackEnvelope(track.id, i)
            # reapy returns list — compare string representations
            if str(check_env) == str(env_id):
                envelope_index = i
                break

        ret = RPR.GetEnvelopeName(env_id, "", 256)
        env_name = ret[2] if isinstance(ret, (list, tuple)) and len(ret) >= 3 else str(ret)
        n_points = RPR.CountEnvelopePoints(env_id)

        return {
            "track_index": track_index,
            "track_name": track.name,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "param_index": param_index,
            "param_name": param_name,
            "envelope_index": envelope_index,
            "envelope_name": env_name,
            "n_points": n_points,
            "activated": activate,
            "default_shape": default_shape,
            "default_shape_name": _SHAPE_NAMES.get(default_shape, "unknown"),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to create FX envelope: {exc}") from exc


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    }
)
def delete_envelope(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
) -> dict:
    """Deactivate and clear an envelope.

    REAPER does not support permanently deleting envelopes via the API.
    This tool clears all points and deactivates the envelope lane.
    The lane still exists in the track but will be invisible and inactive.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        _, _, env_name, _ = RPR.GetEnvelopeName(env_id, "", 256)

        with undo_block(f"Deactivate envelope '{env_name}' on track '{track.name}'"):
            RPR.DeleteEnvelopePointRangeEx(env_id, -1, 0.0, float('inf'))
            _edit_envelope_chunk(env_id, active=False, visible=False)

        return {
            "track_index": track_index,
            "track_name": track.name,
            "envelope_index": envelope_index,
            "envelope_name": env_name,
            "deactivated": True,
            "note": "Envelope lane still exists but is inactive and hidden.",
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to deactivate envelope: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_envelope_properties(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
    active: Annotated[
        bool | None,
        Field(description="Set envelope active state. None to leave unchanged."),
    ] = None,
    visible: Annotated[
        bool | None,
        Field(description="Set envelope visibility. None to leave unchanged."),
    ] = None,
    default_shape: Annotated[
        int | None,
        Field(
            description=(
                "Default point shape: 0=linear, 1=square, 2=slow start/end, "
                "3=fast start, 4=fast end, 5=bezier. None to leave unchanged."
            ),
            ge=0,
            le=5,
        ),
    ] = None,
) -> dict:
    """Modify envelope properties via chunk editing.

    Changes active state, visibility, and/or default point shape.
    At least one of active, visible, or default_shape must be provided.
    """
    try:
        import reapy.reascript_api as RPR

        if active is None and visible is None and default_shape is None:
            raise ToolError(
                "At least one of 'active', 'visible', or 'default_shape' "
                "must be provided."
            )

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        _, _, env_name, _ = RPR.GetEnvelopeName(env_id, "", 256)

        with undo_block(
            f"Set envelope properties on '{env_name}' (track '{track.name}')"
        ):
            _edit_envelope_chunk(
                env_id,
                active=active,
                visible=visible,
                default_shape=default_shape,
            )

        return {
            "track_index": track_index,
            "track_name": track.name,
            "envelope_index": envelope_index,
            "envelope_name": env_name,
            "active": active,
            "visible": visible,
            "default_shape": default_shape,
            "default_shape_name": (
                _SHAPE_NAMES.get(default_shape, "unknown")
                if default_shape is not None
                else None
            ),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set envelope properties: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_fx_envelope_points(
    track_index: TrackIndex,
    envelope_index: EnvelopeIndex,
    points: Annotated[
        list[dict],
        Field(
            description=(
                "List of point objects, each with keys: "
                "'time' (float, seconds), 'value' (float), "
                "and optionally 'shape' (int 0-5, default 0) "
                "and 'tension' (float -1.0 to 1.0, default 0.0)."
            ),
        ),
    ],
    clear_existing: Annotated[
        bool,
        Field(description="If true, delete all existing points before adding new ones"),
    ] = False,
) -> dict:
    """Add multiple points to an envelope in one operation.

    All points are inserted in a single undo block with one final sort
    for efficiency.  Optionally clear all existing points first.
    """
    try:
        import reapy.reascript_api as RPR

        if not points:
            raise ToolError("The 'points' list must not be empty.")

        project = get_project()
        track = validate_track_index(project, track_index)
        env_id = _validate_envelope_index(track, envelope_index)

        _, _, env_name, _ = RPR.GetEnvelopeName(env_id, "", 256)

        # Validate all points before mutating
        validated = []
        for i, pt in enumerate(points):
            if "time" not in pt or "value" not in pt:
                raise ToolError(
                    f"Point at index {i} must have 'time' and 'value' keys."
                )
            time = float(pt["time"])
            value = float(pt["value"])
            shape = int(pt.get("shape", 0))
            tension = float(pt.get("tension", 0.0))

            if time < 0:
                raise ToolError(
                    f"Point at index {i}: time must be >= 0, got {time}."
                )
            if shape < 0 or shape > 5:
                raise ToolError(
                    f"Point at index {i}: shape must be 0-5, got {shape}."
                )
            if tension < -1.0 or tension > 1.0:
                raise ToolError(
                    f"Point at index {i}: tension must be -1.0 to 1.0, "
                    f"got {tension}."
                )
            validated.append((time, value, shape, tension))

        with undo_block(
            f"Add {len(validated)} envelope points to '{env_name}' "
            f"(track '{track.name}')"
        ):
            if clear_existing:
                RPR.DeleteEnvelopePointRangeEx(env_id, -1, 0.0, float('inf'))

            for time, value, shape, tension in validated:
                RPR.InsertEnvelopePoint(
                    env_id, time, value, shape, tension,
                    False,  # selected
                    True,   # noSort -- we sort once after all inserts
                )
            RPR.Envelope_SortPoints(env_id)

        n_points_after = RPR.CountEnvelopePoints(env_id)

        return {
            "track_index": track_index,
            "track_name": track.name,
            "envelope_index": envelope_index,
            "envelope_name": env_name,
            "points_added": len(validated),
            "cleared_existing": clear_existing,
            "total_points": n_points_after,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add envelope points: {exc}") from exc


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
