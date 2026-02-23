"""Shared helpers for the REAPER MCP server."""

from __future__ import annotations

import math
from contextlib import contextmanager

import reapy
from fastmcp.exceptions import ToolError


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_project() -> reapy.Project:
    """Get the current REAPER project. Raises ToolError if REAPER is unreachable."""
    try:
        project = reapy.Project()
        _ = project.name  # force a round-trip to verify connection
        return project
    except Exception as e:
        raise ToolError(
            f"Cannot connect to REAPER. Ensure REAPER is running with the "
            f"reapy extension enabled. Error: {e}"
        )


# ---------------------------------------------------------------------------
# Volume conversion  (REAPER stores linear; tools expose dB)
# ---------------------------------------------------------------------------

_DB_FLOOR = -150.0  # effective silence


def db_to_linear(db: float) -> float:
    """Convert decibels to linear gain (1.0 = 0 dB)."""
    if db <= _DB_FLOOR:
        return 0.0
    return 10.0 ** (db / 20.0)


def linear_to_db(linear: float) -> float:
    """Convert linear gain to decibels."""
    if linear <= 0.0:
        return _DB_FLOOR
    return 20.0 * math.log10(linear)


# ---------------------------------------------------------------------------
# Bounds checking — each returns the object or raises ToolError
# ---------------------------------------------------------------------------

def validate_track_index(project: reapy.Project, idx: int) -> reapy.Track:
    """Return the Track at *idx* or raise ToolError."""
    n = project.n_tracks
    if idx < 0 or idx >= n:
        raise ToolError(
            f"Track index {idx} out of range. "
            f"Project has {n} track{'s' if n != 1 else ''} (valid: 0–{n - 1})."
        )
    return project.tracks[idx]


def validate_fx_index(track: reapy.Track, idx: int) -> reapy.FX:
    """Return the FX at *idx* on *track* or raise ToolError."""
    n = track.n_fxs
    if idx < 0 or idx >= n:
        raise ToolError(
            f"FX index {idx} out of range on track '{track.name}'. "
            f"Track has {n} FX (valid: 0–{n - 1})."
        )
    return track.fxs[idx]


def validate_item_index(track: reapy.Track, idx: int) -> reapy.Item:
    """Return the Item at *idx* on *track* or raise ToolError."""
    n = track.n_items
    if idx < 0 or idx >= n:
        raise ToolError(
            f"Item index {idx} out of range on track '{track.name}'. "
            f"Track has {n} item{'s' if n != 1 else ''} (valid: 0–{n - 1})."
        )
    return track.items[idx]


def validate_send_index(track: reapy.Track, idx: int, category: int = 0):
    """Validate a send index on *track*. category: 0=send, -1=receive."""
    import reapy.reascript_api as RPR
    n = RPR.GetTrackNumSends(track.id, category)
    label = "send" if category == 0 else "receive"
    if idx < 0 or idx >= n:
        raise ToolError(
            f"{label.capitalize()} index {idx} out of range on track '{track.name}'. "
            f"Track has {n} {label}{'s' if n != 1 else ''} (valid: 0–{n - 1})."
        )


# ---------------------------------------------------------------------------
# Undo block helper
# ---------------------------------------------------------------------------

@contextmanager
def undo_block(description: str):
    """Wrap mutations in a REAPER undo block."""
    project = reapy.Project()
    project.begin_undo_block()
    try:
        yield
    finally:
        project.end_undo_block(description)
