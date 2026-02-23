"""Project information and transport control tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project, undo_block

mcp = FastMCP("project")


# ---------------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_project_info() -> dict:
    """Get current REAPER project information.

    Returns project name, file path, BPM, time signature, track count,
    project length, sample rate, and dirty (unsaved changes) flag.
    """
    try:
        project = get_project()
        bpm, beats_per_measure = project.time_signature
        return {
            "name": project.name,
            "path": project.path,
            "bpm": bpm,
            "time_signature": {
                "beats_per_measure": beats_per_measure,
                "beat_value": 4,
            },
            "n_tracks": project.n_tracks,
            "length": project.length,
            "sample_rate": int(project.get_info_value("PROJECT_SRATE")),
            "is_dirty": project.is_dirty,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get project info: {exc}") from exc


# ---------------------------------------------------------------------------
# Transport queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_transport_state() -> dict:
    """Get the current transport state (play, pause, record, cursor position).

    Returns booleans for is_playing, is_paused, is_recording, is_stopped,
    plus the edit cursor position and the current play position in seconds.
    """
    try:
        project = get_project()
        return {
            "is_playing": project.is_playing,
            "is_paused": project.is_paused,
            "is_recording": project.is_recording,
            "is_stopped": not project.is_playing and not project.is_paused and not project.is_recording,
            "cursor_position": project.cursor_position,
            "play_position": project.play_position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get transport state: {exc}") from exc


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_cursor_position(
    position: Annotated[float, Field(description="New cursor position in seconds", ge=0.0)],
) -> dict:
    """Move the edit cursor to the specified position in seconds."""
    try:
        project = get_project()
        with undo_block("Set cursor position"):
            project.cursor_position = position
        return {
            "cursor_position": project.cursor_position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set cursor position: {exc}") from exc


# ---------------------------------------------------------------------------
# Transport actions
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def transport_play() -> dict:
    """Start playback in the current project."""
    try:
        project = get_project()
        project.play()
        return {"status": "playing"}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to start playback: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def transport_stop() -> dict:
    """Stop playback or recording in the current project."""
    try:
        project = get_project()
        project.stop()
        return {"status": "stopped"}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to stop transport: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def transport_pause() -> dict:
    """Pause playback in the current project."""
    try:
        project = get_project()
        project.pause()
        return {"status": "paused"}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to pause transport: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def transport_record() -> dict:
    """Start recording in the current project.

    WARNING: This is a destructive operation that writes audio data to disk.
    Ensure record-armed tracks and input monitoring are configured correctly.
    """
    try:
        project = get_project()
        project.record()
        return {"status": "recording"}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to start recording: {exc}") from exc


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def save_project(
    path: Annotated[
        str | None,
        Field(description="Optional file path to save as. If omitted, saves to the current project path."),
    ] = None,
) -> dict:
    """Save the current project, optionally to a new file path."""
    try:
        project = get_project()
        if path is not None:
            project.save(path)
        else:
            project.save()
        return {
            "saved": True,
            "path": path or project.path,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to save project: {exc}") from exc
