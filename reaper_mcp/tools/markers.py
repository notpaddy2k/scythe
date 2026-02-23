"""Marker and region tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import reapy
import reapy.reascript_api as RPR

from reaper_mcp.helpers import get_project, undo_block

mcp = FastMCP("markers")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

ColorChannel = Annotated[int, Field(ge=0, le=255)]
MarkerIndex = Annotated[int, Field(description="Zero-based marker/region index", ge=0)]
Position = Annotated[float, Field(description="Position in seconds", ge=0.0)]


# ---------------------------------------------------------------------------
# Read-only queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_markers() -> dict:
    """List all markers in the current REAPER project.

    Returns each marker's index, position in seconds, name, and RGB color.
    """
    try:
        project = get_project()
        markers = [
            {
                "index": m.index,
                "position": m.position,
                "name": m.name,
                "color": m.color,
            }
            for m in project.markers
        ]
        return {"n_markers": len(markers), "markers": markers}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list markers: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_regions() -> dict:
    """List all regions in the current REAPER project.

    Returns each region's index, start/end positions in seconds, name,
    and RGB color.
    """
    try:
        project = get_project()
        regions = [
            {
                "index": r.index,
                "start": r.start,
                "end": r.end,
                "name": r.name,
                "color": r.color,
            }
            for r in project.regions
        ]
        return {"n_regions": len(regions), "regions": regions}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list regions: {exc}") from exc


# ---------------------------------------------------------------------------
# Marker / region creation
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_marker(
    position: Position,
    name: Annotated[str, Field(description="Display name for the marker")] = "",
    r: Annotated[ColorChannel, Field(description="Red channel (0-255)")] = 0,
    g: Annotated[ColorChannel, Field(description="Green channel (0-255)")] = 0,
    b: Annotated[ColorChannel, Field(description="Blue channel (0-255)")] = 0,
) -> dict:
    """Add a marker at the specified position in seconds.

    Optionally provide a name and an RGB color. If all color channels are
    zero the marker uses the default REAPER color.
    """
    try:
        project = get_project()
        color = (r, g, b) if any((r, g, b)) else 0
        with undo_block("Add marker"):
            marker = project.add_marker(position, name=name, color=color)
        return {
            "index": marker.index,
            "position": marker.position,
            "name": marker.name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add marker: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_region(
    start: Annotated[float, Field(description="Region start position in seconds", ge=0.0)],
    end: Annotated[float, Field(description="Region end position in seconds", ge=0.0)],
    name: Annotated[str, Field(description="Display name for the region")] = "",
    r: Annotated[ColorChannel, Field(description="Red channel (0-255)")] = 0,
    g: Annotated[ColorChannel, Field(description="Green channel (0-255)")] = 0,
    b: Annotated[ColorChannel, Field(description="Blue channel (0-255)")] = 0,
) -> dict:
    """Add a region spanning from *start* to *end* in seconds.

    Optionally provide a name and an RGB color. If all color channels are
    zero the region uses the default REAPER color.
    """
    if end <= start:
        raise ToolError(
            f"Region end ({end}) must be greater than start ({start})."
        )
    try:
        project = get_project()
        color = (r, g, b) if any((r, g, b)) else 0
        with undo_block("Add region"):
            region = project.add_region(start, end, name=name, color=color)
        return {
            "index": region.index,
            "start": region.start,
            "end": region.end,
            "name": region.name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add region: {exc}") from exc


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_marker_or_region(
    index: MarkerIndex,
    is_region: Annotated[
        bool,
        Field(description="True to delete a region, False to delete a marker"),
    ] = False,
) -> dict:
    """Delete a marker or region by its index.

    WARNING: This permanently removes the marker or region. Use *is_region*
    to indicate whether the index refers to a region (True) or a marker
    (False, the default).
    """
    try:
        project = get_project()
        with undo_block("Delete marker/region"):
            ok = RPR.DeleteProjectMarker(project.id, index, is_region)
        if not ok:
            kind = "region" if is_region else "marker"
            raise ToolError(
                f"Failed to delete {kind} at index {index}. "
                f"Check that the index exists."
            )
        return {
            "deleted_index": index,
            "was_region": is_region,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete marker/region: {exc}") from exc


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def go_to_marker(
    marker_index: Annotated[
        int,
        Field(description="Marker number to navigate to (as shown in REAPER)"),
    ],
) -> dict:
    """Move the edit cursor to the specified marker number.

    The marker_index corresponds to the marker number displayed in REAPER,
    not the internal zero-based index.
    """
    try:
        project = get_project()
        RPR.GoToMarker(project.id, marker_index, False)
        return {
            "navigated_to_marker": marker_index,
            "cursor_position": project.cursor_position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to navigate to marker {marker_index}: {exc}") from exc
