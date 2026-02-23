"""Rendering and media import tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project, validate_track_index, undo_block

mcp = FastMCP("render")


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

TrackIndex = Annotated[int, Field(description="Zero-based track index", ge=0)]


# ---------------------------------------------------------------------------
# Media / render tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def insert_media(
    track_index: TrackIndex,
    file_path: Annotated[str, Field(description="Absolute path to the media file to insert")],
    position: Annotated[float, Field(description="Position in seconds to insert the media at", ge=0.0)],
) -> dict:
    """Insert a media file onto a track at a given time position.

    The file is added to the specified track at the given position (seconds).
    Supported formats depend on REAPER's installed decoders (WAV, MP3, FLAC,
    MIDI, etc.).
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        import reapy.reascript_api as RPR

        with undo_block("Insert media"):
            project.cursor_position = position
            # Unselect all tracks, then select only the target track
            for t in project.tracks:
                RPR.SetTrackSelected(t.id, False)
            RPR.SetTrackSelected(track.id, True)
            RPR.InsertMedia(file_path, 0)
        return {
            "track_index": track_index,
            "file_path": file_path,
            "position": position,
            "inserted": True,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to insert media: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def render_project() -> dict:
    """Render the project using the current render settings.

    Executes REAPER's built-in render command (action 41824) which uses the
    most recently configured render settings (format, path, bounds, etc.).
    Configure render settings in REAPER before calling this tool.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        RPR.Main_OnCommand(41824, 0)
        return {
            "rendered": True,
            "note": "Rendered with current render settings",
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to render project: {exc}") from exc
