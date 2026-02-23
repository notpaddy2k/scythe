"""Media item tools for REAPER."""

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
    validate_item_index,
    undo_block,
)

mcp = FastMCP("items")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

TrackIndex = Annotated[int, Field(description="Zero-based track index", ge=0)]
ItemIndex = Annotated[int, Field(description="Zero-based item index on the track", ge=0)]
Position = Annotated[float, Field(description="Position in seconds", ge=0.0)]
Length = Annotated[float, Field(description="Length in seconds", gt=0.0)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _item_summary(item, index: int) -> dict:
    """Build a summary dict for a single media item."""
    active_take_name = ""
    try:
        take = item.active_take
        if take is not None:
            active_take_name = take.name
    except Exception:
        pass

    return {
        "index": index,
        "position": item.position,
        "length": item.length,
        "n_takes": item.n_takes if hasattr(item, "n_takes") else 0,
        "active_take_name": active_take_name,
    }


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_items_on_track(
    track_index: TrackIndex,
) -> dict:
    """List all media items on the specified track.

    Returns each item's index, position, length, number of takes, and
    the active take name.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        items = [
            _item_summary(item, idx)
            for idx, item in enumerate(track.items)
        ]
        return {
            "track_index": track_index,
            "track_name": track.name,
            "n_items": len(items),
            "items": items,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list items on track {track_index}: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_selected_items() -> dict:
    """Get all currently selected media items across all tracks.

    Returns each item's position, length, and the index of the track
    it belongs to.
    """
    try:
        project = get_project()
        n_selected = RPR.CountSelectedMediaItems(project.id)
        items = []
        for i in range(n_selected):
            item_id = RPR.GetSelectedMediaItem(project.id, i)
            position = RPR.GetMediaItemInfo_Value(item_id, "D_POSITION")
            length = RPR.GetMediaItemInfo_Value(item_id, "D_LENGTH")
            track_id = RPR.GetMediaItemTrack(item_id)
            track_number = RPR.GetMediaTrackInfo_Value(track_id, "IP_TRACKNUMBER")
            # IP_TRACKNUMBER is 1-based; convert to 0-based index
            track_idx = int(track_number) - 1
            items.append({
                "selection_index": i,
                "position": position,
                "length": length,
                "track_index": track_idx,
            })
        return {"n_selected": n_selected, "items": items}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get selected items: {exc}") from exc


# ---------------------------------------------------------------------------
# Item creation
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_empty_item(
    track_index: TrackIndex,
    position: Position,
    length: Length,
) -> dict:
    """Add an empty media item to the specified track.

    The item will have no takes. Use this to create placeholder items or
    containers that can receive audio/MIDI data later.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Add empty item"):
            item = track.add_item(start=position, length=length)
        return {
            "track_index": track_index,
            "position": item.position,
            "length": item.length,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add empty item: {exc}") from exc


# ---------------------------------------------------------------------------
# Item deletion
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_item(
    track_index: TrackIndex,
    item_index: ItemIndex,
) -> dict:
    """Delete a media item from the specified track.

    WARNING: This permanently removes the item and all its takes. This
    action cannot be undone if the undo history is exhausted.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        deleted_position = item.position
        deleted_length = item.length
        with undo_block("Delete media item"):
            RPR.DeleteTrackMediaItem(track.id, item.id)
        return {
            "track_index": track_index,
            "deleted_item_index": item_index,
            "deleted_position": deleted_position,
            "deleted_length": deleted_length,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete item: {exc}") from exc


# ---------------------------------------------------------------------------
# Item property setters
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_item_position(
    track_index: TrackIndex,
    item_index: ItemIndex,
    position: Position,
) -> dict:
    """Move a media item to a new position in seconds."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        with undo_block("Set item position"):
            item.position = position
        return {
            "track_index": track_index,
            "item_index": item_index,
            "position": item.position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set item position: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_item_length(
    track_index: TrackIndex,
    item_index: ItemIndex,
    length: Length,
) -> dict:
    """Set the length of a media item in seconds."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        with undo_block("Set item length"):
            item.length = length
        return {
            "track_index": track_index,
            "item_index": item_index,
            "length": item.length,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set item length: {exc}") from exc


# ---------------------------------------------------------------------------
# Item splitting
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def split_item(
    track_index: TrackIndex,
    item_index: ItemIndex,
    position: Annotated[
        float,
        Field(
            description=(
                "Split point in seconds (absolute timeline position). "
                "Must be within the item's start and end boundaries."
            ),
            ge=0.0,
        ),
    ],
) -> dict:
    """Split a media item at the specified position.

    The original item is trimmed to end at the split point, and a new item
    is created starting at the split point with the remaining content.

    The position must fall within the item's start and end boundaries.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)

        item_start = item.position
        item_end = item_start + item.length

        if position <= item_start or position >= item_end:
            raise ToolError(
                f"Split position {position} is outside the item boundaries "
                f"({item_start} - {item_end}). Position must be strictly "
                f"between the item's start and end."
            )

        with undo_block("Split media item"):
            new_item_id = RPR.SplitMediaItem(item.id, position)

        if not new_item_id:
            raise ToolError(
                f"REAPER refused to split the item at position {position}."
            )

        return {
            "track_index": track_index,
            "original_item_index": item_index,
            "split_position": position,
            "left_item_end": position,
            "right_item_start": position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to split item: {exc}") from exc
