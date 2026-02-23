"""MIDI note and CC editing tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import (
    get_project,
    validate_track_index,
    validate_item_index,
    undo_block,
)

mcp = FastMCP("midi")

# ---------------------------------------------------------------------------
# Type aliases for annotated parameters
# ---------------------------------------------------------------------------

TrackIndex = Annotated[int, Field(description="Zero-based track index", ge=0)]
ItemIndex = Annotated[int, Field(description="Zero-based item index on the track", ge=0)]
NoteIndex = Annotated[int, Field(description="Zero-based note index within the MIDI take", ge=0)]
CCIndex = Annotated[int, Field(description="Zero-based CC event index within the MIDI take", ge=0)]
Pitch = Annotated[int, Field(description="MIDI note number (0-127, where 60 = middle C)", ge=0, le=127)]
Velocity = Annotated[int, Field(description="MIDI velocity (1-127)", ge=1, le=127)]
Channel = Annotated[int, Field(description="MIDI channel (0-15)", ge=0, le=15)]
PPQ = Annotated[int, Field(description="Position in PPQ (pulses per quarter note) ticks", ge=0)]
CCNumber = Annotated[int, Field(description="MIDI CC number (0-127)", ge=0, le=127)]
CCValue = Annotated[int, Field(description="MIDI CC value (0-127)", ge=0, le=127)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_take(track, item):
    """Return the active take from an item, or raise ToolError if none."""
    take = item.active_take
    if take is None:
        raise ToolError(
            f"Item {item} on track '{track.name}' has no active take."
        )
    return take


# ---------------------------------------------------------------------------
# MIDI item creation
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def create_midi_item(
    track_index: TrackIndex,
    position: Annotated[float, Field(description="Start position in seconds", ge=0.0)],
    length: Annotated[float, Field(description="Length of the MIDI item in seconds", gt=0.0)],
) -> dict:
    """Create a new empty MIDI item on a track.

    Returns the position and length of the newly created item.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block("Create MIDI item"):
            RPR.CreateNewMIDIItemInProj(track.id, position, position + length)
        return {
            "track_index": track_index,
            "position": position,
            "length": length,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to create MIDI item: {exc}") from exc


# ---------------------------------------------------------------------------
# MIDI note queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_midi_notes(
    track_index: TrackIndex,
    item_index: ItemIndex,
) -> dict:
    """List all MIDI notes in an item's active take.

    Returns each note's index, pitch, velocity, start/end PPQ positions,
    channel, muted state, and selected state.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        _, note_count, _, _ = RPR.MIDI_CountEvts(take.id)

        notes = []
        for i in range(note_count):
            (
                _retval, _take_id, _note_idx,
                selected, muted,
                start_ppq, end_ppq,
                channel, pitch, velocity,
            ) = RPR.MIDI_GetNote(take.id, i)
            notes.append({
                "index": i,
                "pitch": pitch,
                "velocity": velocity,
                "start_ppq": start_ppq,
                "end_ppq": end_ppq,
                "channel": channel,
                "muted": muted,
                "selected": selected,
            })
        return {"n_notes": note_count, "notes": notes}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list MIDI notes: {exc}") from exc


# ---------------------------------------------------------------------------
# MIDI note mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_midi_note(
    track_index: TrackIndex,
    item_index: ItemIndex,
    pitch: Pitch,
    velocity: Velocity,
    start_ppq: PPQ,
    end_ppq: Annotated[int, Field(description="End position in PPQ ticks (must be > start_ppq)", gt=0)],
    channel: Channel = 0,
    selected: Annotated[bool, Field(description="Whether the note is selected")] = False,
    muted: Annotated[bool, Field(description="Whether the note is muted")] = False,
) -> dict:
    """Add a MIDI note to an item's active take.

    The note is inserted and the MIDI data is sorted afterwards.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        with undo_block("Add MIDI note"):
            RPR.MIDI_InsertNote(
                take.id, selected, muted,
                start_ppq, end_ppq,
                channel, pitch, velocity,
                True,  # noSortIn — we sort manually after
            )
            RPR.MIDI_Sort(take.id)
        return {
            "pitch": pitch,
            "velocity": velocity,
            "start_ppq": start_ppq,
            "end_ppq": end_ppq,
            "channel": channel,
            "selected": selected,
            "muted": muted,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add MIDI note: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_midi_note(
    track_index: TrackIndex,
    item_index: ItemIndex,
    note_index: NoteIndex,
) -> dict:
    """Delete a MIDI note by index from an item's active take.

    WARNING: Note indices may shift after deletion. Re-query with
    list_midi_notes to get updated indices.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        _, note_count, _, _ = RPR.MIDI_CountEvts(take.id)
        if note_index < 0 or note_index >= note_count:
            raise ToolError(
                f"Note index {note_index} out of range. "
                f"Take has {note_count} note{'s' if note_count != 1 else ''} "
                f"(valid: 0-{note_count - 1})."
            )

        with undo_block("Delete MIDI note"):
            RPR.MIDI_DeleteNote(take.id, note_index)
        return {"deleted_note_index": note_index}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete MIDI note: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_midi_note(
    track_index: TrackIndex,
    item_index: ItemIndex,
    note_index: NoteIndex,
    pitch: Annotated[int | None, Field(description="New pitch (0-127). Omit to keep current.", ge=0, le=127)] = None,
    velocity: Annotated[int | None, Field(description="New velocity (1-127). Omit to keep current.", ge=1, le=127)] = None,
    start_ppq: Annotated[int | None, Field(description="New start PPQ. Omit to keep current.", ge=0)] = None,
    end_ppq: Annotated[int | None, Field(description="New end PPQ. Omit to keep current.", gt=0)] = None,
    channel: Annotated[int | None, Field(description="New channel (0-15). Omit to keep current.", ge=0, le=15)] = None,
    muted: Annotated[bool | None, Field(description="New muted state. Omit to keep current.")] = None,
) -> dict:
    """Edit an existing MIDI note's properties.

    Only provided fields are changed; omitted fields keep their current
    values. The MIDI data is re-sorted after modification.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        _, note_count, _, _ = RPR.MIDI_CountEvts(take.id)
        if note_index < 0 or note_index >= note_count:
            raise ToolError(
                f"Note index {note_index} out of range. "
                f"Take has {note_count} note{'s' if note_count != 1 else ''} "
                f"(valid: 0-{note_count - 1})."
            )

        # Read current note values
        (
            _retval, _take_id, _note_idx,
            cur_selected, cur_muted,
            cur_start_ppq, cur_end_ppq,
            cur_channel, cur_pitch, cur_velocity,
        ) = RPR.MIDI_GetNote(take.id, note_index)

        # Apply only the fields that were explicitly provided
        new_pitch = pitch if pitch is not None else cur_pitch
        new_velocity = velocity if velocity is not None else cur_velocity
        new_start_ppq = start_ppq if start_ppq is not None else cur_start_ppq
        new_end_ppq = end_ppq if end_ppq is not None else cur_end_ppq
        new_channel = channel if channel is not None else cur_channel
        new_muted = muted if muted is not None else cur_muted

        with undo_block("Set MIDI note"):
            RPR.MIDI_SetNote(
                take.id, note_index,
                cur_selected, new_muted,
                new_start_ppq, new_end_ppq,
                new_channel, new_pitch, new_velocity,
                True,  # noSortIn
            )
            RPR.MIDI_Sort(take.id)
        return {
            "note_index": note_index,
            "pitch": new_pitch,
            "velocity": new_velocity,
            "start_ppq": new_start_ppq,
            "end_ppq": new_end_ppq,
            "channel": new_channel,
            "muted": new_muted,
            "selected": cur_selected,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set MIDI note: {exc}") from exc


# ---------------------------------------------------------------------------
# MIDI CC queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_midi_cc(
    track_index: TrackIndex,
    item_index: ItemIndex,
) -> dict:
    """List all MIDI CC events in an item's active take.

    Returns each CC event's index, ppq position, CC number (msg2),
    CC value (msg3), channel, channel message type, muted state,
    and selected state.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        _, _, cc_count, _ = RPR.MIDI_CountEvts(take.id)

        events = []
        for i in range(cc_count):
            (
                _retval, _take_id, _cc_idx,
                selected, muted,
                ppqpos, chanmsg, channel, msg2, msg3,
            ) = RPR.MIDI_GetCC(take.id, i)
            events.append({
                "index": i,
                "ppq_position": ppqpos,
                "cc_num": msg2,
                "value": msg3,
                "channel": channel,
                "chanmsg": chanmsg,
                "muted": muted,
                "selected": selected,
            })
        return {"n_cc_events": cc_count, "cc_events": events}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list MIDI CC events: {exc}") from exc


# ---------------------------------------------------------------------------
# MIDI CC mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_midi_cc(
    track_index: TrackIndex,
    item_index: ItemIndex,
    cc_num: CCNumber,
    value: CCValue,
    ppq_position: PPQ,
    channel: Channel = 0,
) -> dict:
    """Add a MIDI CC event to an item's active take.

    Inserts a Control Change message (status byte 0xB0 / 176) and sorts
    the MIDI data afterwards.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        with undo_block("Add MIDI CC"):
            RPR.MIDI_InsertCC(
                take.id,
                False,  # selected
                False,  # muted
                ppq_position,
                176,    # chanmsg: 0xB0 = Control Change
                channel,
                cc_num,
                value,
            )
            RPR.MIDI_Sort(take.id)
        return {
            "cc_num": cc_num,
            "value": value,
            "ppq_position": ppq_position,
            "channel": channel,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add MIDI CC event: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False})
def delete_midi_cc(
    track_index: TrackIndex,
    item_index: ItemIndex,
    cc_index: CCIndex,
) -> dict:
    """Delete a MIDI CC event by index from an item's active take.

    WARNING: CC event indices may shift after deletion. Re-query with
    list_midi_cc to get updated indices.
    """
    try:
        import reapy.reascript_api as RPR

        project = get_project()
        track = validate_track_index(project, track_index)
        item = validate_item_index(track, item_index)
        take = _get_active_take(track, item)

        _, _, cc_count, _ = RPR.MIDI_CountEvts(take.id)
        if cc_index < 0 or cc_index >= cc_count:
            raise ToolError(
                f"CC index {cc_index} out of range. "
                f"Take has {cc_count} CC event{'s' if cc_count != 1 else ''} "
                f"(valid: 0-{cc_count - 1})."
            )

        with undo_block("Delete MIDI CC"):
            RPR.MIDI_DeleteCC(take.id, cc_index)
        return {"deleted_cc_index": cc_index}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to delete MIDI CC event: {exc}") from exc
