"""Track send, receive, and hardware output tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
import reapy
import reapy.reascript_api as RPR

from reaper_mcp.helpers import (
    get_project,
    validate_track_index,
    validate_send_index,
    db_to_linear,
    linear_to_db,
    undo_block,
)

mcp = FastMCP("sends")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Send category constants used by the REAPER API
_CATEGORY_SEND = 0
_CATEGORY_RECEIVE = -1
_CATEGORY_HARDWARE = 1


def _get_send_info(track: reapy.Track, category: int, index: int) -> dict:
    """Collect info for a single send/receive at the given index."""
    vol_linear = RPR.GetTrackSendInfo_Value(
        track.id, category, index, "D_VOL"
    )
    pan = RPR.GetTrackSendInfo_Value(
        track.id, category, index, "D_PAN"
    )
    muted = bool(
        RPR.GetTrackSendInfo_Value(track.id, category, index, "B_MUTE")
    )

    # Resolve destination/source track name
    dest_name = None
    try:
        if category == _CATEGORY_SEND:
            # For sends, use reapy's send list if available
            sends = track.sends
            if index < len(sends):
                dest_name = sends[index].dest_track.name
        elif category == _CATEGORY_RECEIVE:
            # For receives, try to get the source track via RPR
            # P_SRCTRACK on receives gives the source track pointer
            src_ptr = RPR.GetTrackSendInfo_Value(
                track.id, category, index, "P_SRCTRACK"
            )
            if src_ptr:
                _, src_name, _ = RPR.GetTrackName(int(src_ptr), "", 256)
                dest_name = src_name
    except Exception:
        dest_name = None

    return {
        "index": index,
        "dest_track": dest_name,
        "volume_db": round(linear_to_db(vol_linear), 2),
        "pan": round(pan, 4),
        "muted": muted,
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_track_sends(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
) -> dict:
    """List all sends on a track.

    Returns each send's index, destination track name, volume in dB,
    pan position (-1.0 left to 1.0 right), and mute state.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        n_sends = RPR.GetTrackNumSends(track.id, _CATEGORY_SEND)
        sends = []
        for i in range(n_sends):
            sends.append(_get_send_info(track, _CATEGORY_SEND, i))
        return {
            "track_index": track_index,
            "track_name": track.name,
            "n_sends": n_sends,
            "sends": sends,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list track sends: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_track_receives(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
) -> dict:
    """List all receives on a track.

    Returns each receive's index, source track name, volume in dB,
    pan position, and mute state.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        n_receives = RPR.GetTrackNumSends(track.id, _CATEGORY_RECEIVE)
        receives = []
        for i in range(n_receives):
            info = _get_send_info(track, _CATEGORY_RECEIVE, i)
            # Rename key for clarity in receives context
            info["src_track"] = info.pop("dest_track")
            receives.append(info)
        return {
            "track_index": track_index,
            "track_name": track.name,
            "n_receives": n_receives,
            "receives": receives,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list track receives: {exc}") from exc


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def create_send(
    src_track_index: Annotated[int, Field(description="Zero-based source track index", ge=0)],
    dst_track_index: Annotated[int, Field(description="Zero-based destination track index", ge=0)],
) -> dict:
    """Create a new send from one track to another.

    Returns the new send index on the source track.
    """
    try:
        project = get_project()
        src_track = validate_track_index(project, src_track_index)
        dst_track = validate_track_index(project, dst_track_index)
        if src_track_index == dst_track_index:
            raise ToolError("Cannot create a send from a track to itself.")
        with undo_block(
            f"Create send from '{src_track.name}' to '{dst_track.name}'"
        ):
            send_index = RPR.CreateTrackSend(src_track.id, dst_track.id)
        if send_index < 0:
            raise ToolError(
                f"Failed to create send from track '{src_track.name}' "
                f"to track '{dst_track.name}'."
            )
        return {
            "src_track_index": src_track_index,
            "src_track_name": src_track.name,
            "dst_track_index": dst_track_index,
            "dst_track_name": dst_track.name,
            "send_index": send_index,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to create send: {exc}") from exc


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    }
)
def remove_send(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    send_index: Annotated[int, Field(description="Zero-based send index on the track", ge=0)],
) -> dict:
    """Remove a send from a track.

    WARNING: This permanently removes the send. Subsequent send indices
    will shift down by one.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        validate_send_index(track, send_index, category=_CATEGORY_SEND)

        # Capture destination name before removal
        dest_name = None
        try:
            sends = track.sends
            if send_index < len(sends):
                dest_name = sends[send_index].dest_track.name
        except Exception:
            pass

        with undo_block(
            f"Remove send {send_index} from track '{track.name}'"
        ):
            RPR.RemoveTrackSend(track.id, _CATEGORY_SEND, send_index)

        return {
            "track_index": track_index,
            "track_name": track.name,
            "removed_send_index": send_index,
            "removed_dest_track": dest_name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to remove send: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_send_volume_pan(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    send_index: Annotated[int, Field(description="Zero-based send index on the track", ge=0)],
    volume_db: Annotated[
        float | None,
        Field(description="Send volume in dB (0.0 = unity, -inf = silence). Omit to leave unchanged."),
    ] = None,
    pan: Annotated[
        float | None,
        Field(description="Send pan position (-1.0 = full left, 0.0 = center, 1.0 = full right). Omit to leave unchanged.", ge=-1.0, le=1.0),
    ] = None,
) -> dict:
    """Set volume and/or pan on a track send.

    At least one of volume_db or pan must be provided. Volume is specified
    in decibels (0.0 = unity gain). Pan ranges from -1.0 (left) to 1.0 (right).
    """
    try:
        if volume_db is None and pan is None:
            raise ToolError(
                "Provide at least one of 'volume_db' or 'pan'."
            )

        project = get_project()
        track = validate_track_index(project, track_index)
        validate_send_index(track, send_index, category=_CATEGORY_SEND)

        changes = []
        with undo_block(
            f"Set send {send_index} vol/pan on track '{track.name}'"
        ):
            if volume_db is not None:
                linear = db_to_linear(volume_db)
                RPR.SetTrackSendInfo_Value(
                    track.id, _CATEGORY_SEND, send_index, "D_VOL", linear
                )
                changes.append(f"volume={volume_db:.2f} dB")

            if pan is not None:
                RPR.SetTrackSendInfo_Value(
                    track.id, _CATEGORY_SEND, send_index, "D_PAN", pan
                )
                changes.append(f"pan={pan:.4f}")

        # Read back current values for confirmation
        current_vol = RPR.GetTrackSendInfo_Value(
            track.id, _CATEGORY_SEND, send_index, "D_VOL"
        )
        current_pan = RPR.GetTrackSendInfo_Value(
            track.id, _CATEGORY_SEND, send_index, "D_PAN"
        )

        return {
            "track_index": track_index,
            "track_name": track.name,
            "send_index": send_index,
            "volume_db": round(linear_to_db(current_vol), 2),
            "pan": round(current_pan, 4),
            "changes_applied": changes,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set send volume/pan: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_send_mute(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    send_index: Annotated[int, Field(description="Zero-based send index on the track", ge=0)],
    muted: Annotated[bool, Field(description="True to mute the send, False to unmute")],
) -> dict:
    """Mute or unmute a track send."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        validate_send_index(track, send_index, category=_CATEGORY_SEND)

        with undo_block(
            f"{'Mute' if muted else 'Unmute'} send {send_index} on track '{track.name}'"
        ):
            RPR.SetTrackSendInfo_Value(
                track.id, _CATEGORY_SEND, send_index, "B_MUTE", float(muted)
            )

        return {
            "track_index": track_index,
            "track_name": track.name,
            "send_index": send_index,
            "muted": muted,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set send mute: {exc}") from exc
