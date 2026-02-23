"""Track management tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import (
    get_project,
    validate_track_index,
    db_to_linear,
    linear_to_db,
    undo_block,
)

mcp = FastMCP("tracks")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

TrackIndex = Annotated[int, Field(description="Zero-based track index", ge=0)]
VolumeDb = Annotated[float, Field(description="Volume in decibels (0.0 = unity gain)")]
PanValue = Annotated[
    float,
    Field(description="Pan value from -1.0 (full left) to 1.0 (full right)", ge=-1.0, le=1.0),
]
ColorChannel = Annotated[int, Field(ge=0, le=255)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _track_summary(track, index: int) -> dict:
    """Build a summary dict for a single track."""
    return {
        "index": index,
        "name": track.name,
        "volume_db": linear_to_db(track.get_info_value("D_VOL")),
        "pan": track.get_info_value("D_PAN"),
        "muted": track.is_muted,
        "soloed": track.is_solo,
        "armed": bool(track.get_info_value("I_RECARM")),
        "color": track.color,
        "n_fxs": track.n_fxs,
    }


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_tracks() -> dict:
    """List all tracks in the current REAPER project.

    Returns a summary of each track including name, volume, pan, mute/solo
    state, record arm status, color, and FX count.
    """
    try:
        project = get_project()
        tracks = [
            _track_summary(track, idx)
            for idx, track in enumerate(project.tracks)
        ]
        return {"n_tracks": project.n_tracks, "tracks": tracks}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list tracks: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_track_info(
    track_index: TrackIndex,
) -> dict:
    """Get detailed information about a single track.

    Returns all summary fields plus item count and automation mode.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        info = _track_summary(track, track_index)
        info["n_items"] = track.n_items
        info["automation_mode"] = int(track.get_info_value("I_AUTOMODE"))
        return info
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get track info: {exc}") from exc


# ---------------------------------------------------------------------------
# Track creation / deletion
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_track(
    index: Annotated[
        int | None,
        Field(description="Position to insert the new track (zero-based). Defaults to end of track list."),
    ] = None,
    name: Annotated[
        str | None,
        Field(description="Name for the new track. Defaults to empty string."),
    ] = None,
) -> dict:
    """Add a new track to the project at the given index."""
    try:
        project = get_project()
        insert_at = index if index is not None else project.n_tracks
        track_name = name or ""
        with undo_block("Add track"):
            project.add_track(index=insert_at, name=track_name)
        return {
            "index": insert_at,
            "name": track_name,
            "n_tracks": project.n_tracks,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add track: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_track(
    track_index: TrackIndex,
) -> dict:
    """Delete a track from the project.

    WARNING: This permanently removes the track and all its items, FX, and
    automation data. This action cannot be undone if the undo history is
    exhausted.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        deleted_name = track.name
        with undo_block("Delete track"):
            track.delete()
        return {
            "deleted_index": track_index,
            "deleted_name": deleted_name,
            "n_tracks": project.n_tracks,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete track: {exc}") from exc


# ---------------------------------------------------------------------------
# Track property setters
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_name(
    track_index: TrackIndex,
    name: Annotated[str, Field(description="New name for the track")],
) -> dict:
    """Rename a track."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track name"):
            track.name = name
        return {"index": track_index, "name": track.name}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track name: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_volume(
    track_index: TrackIndex,
    volume_db: VolumeDb,
) -> dict:
    """Set a track's volume in decibels (0.0 dB = unity gain)."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track volume"):
            track.set_info_value("D_VOL", db_to_linear(volume_db))
        return {
            "index": track_index,
            "volume_db": linear_to_db(track.get_info_value("D_VOL")),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track volume: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_pan(
    track_index: TrackIndex,
    pan: PanValue,
) -> dict:
    """Set a track's pan position (-1.0 = full left, 0.0 = center, 1.0 = full right)."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track pan"):
            track.set_info_value("D_PAN", pan)
        return {
            "index": track_index,
            "pan": track.get_info_value("D_PAN"),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track pan: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_mute_solo(
    track_index: TrackIndex,
    mute: Annotated[
        bool | None,
        Field(description="Set mute state. Pass null/omit to leave unchanged."),
    ] = None,
    solo: Annotated[
        bool | None,
        Field(description="Set solo state. Pass null/omit to leave unchanged."),
    ] = None,
) -> dict:
    """Set the mute and/or solo state on a track.

    Either or both of mute and solo can be provided. Omitted values are
    left unchanged.
    """
    if mute is None and solo is None:
        raise ToolError("At least one of 'mute' or 'solo' must be provided.")
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track mute/solo"):
            if mute is not None:
                track.is_muted = mute
            if solo is not None:
                track.is_solo = solo
        return {
            "index": track_index,
            "muted": track.is_muted,
            "soloed": track.is_solo,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track mute/solo: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_record_arm(
    track_index: TrackIndex,
    armed: Annotated[bool, Field(description="True to arm, False to disarm")],
) -> dict:
    """Arm or disarm a track for recording."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track record arm"):
            track.set_info_value("I_RECARM", int(armed))
        return {
            "index": track_index,
            "armed": bool(track.get_info_value("I_RECARM")),
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track record arm: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_color(
    track_index: TrackIndex,
    r: Annotated[ColorChannel, Field(description="Red channel (0-255)")],
    g: Annotated[ColorChannel, Field(description="Green channel (0-255)")],
    b: Annotated[ColorChannel, Field(description="Blue channel (0-255)")],
) -> dict:
    """Set a track's display color using RGB values (0-255 per channel)."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Set track color"):
            track.color = (r, g, b)
        return {
            "index": track_index,
            "color": track.color,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set track color: {exc}") from exc
