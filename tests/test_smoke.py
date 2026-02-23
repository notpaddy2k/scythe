"""Smoke tests for Scythe — run with REAPER open and reapy server active.

Creates a fresh empty project tab, runs all tests there, then closes it
so the user's original project is never touched.

Usage:
    python tests/test_smoke.py

Requirements:
    - REAPER running with "Activate reapy server" action active
    - python-reapy and fastmcp installed
"""

import os
import sys
import traceback

# Bootstrap imports so this works from repo root without pip install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reapy
import reapy.reascript_api as RPR

from scythe.tools import (
    project,
    tracks,
    track_fx,
    sends,
    markers,
    tempo,
    items,
    midi,
    envelopes,
    time_selection,
    actions,
    ext_state,
    devices,
    render,
)

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def run_test(name: str, fn):
    """Run a test function, catch exceptions, record result."""
    try:
        fn()
        _results.append((name, True, ""))
        print(f"  PASS  {name}")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        _results.append((name, False, msg))
        print(f"  FAIL  {name}")
        print(f"        {msg}")
        if os.environ.get("SCYTHE_TEST_VERBOSE"):
            traceback.print_exc()


# ---------------------------------------------------------------------------
# Project isolation — create & teardown a scratch project tab
# ---------------------------------------------------------------------------

_original_project_name: str = ""


def setup_test_project():
    """Open a new empty project tab for testing.

    REAPER action 41929 = 'New project tab'.  This leaves the user's
    current project untouched in its own tab.
    """
    global _original_project_name
    _original_project_name = reapy.Project().name or "(untitled)"
    RPR.Main_OnCommand(41929, 0)  # New project tab
    # The new (empty) project is now the active one
    p = reapy.Project()
    print(f"  Test project created: {p.name or '(empty)'}")


def teardown_test_project():
    """Close the scratch project tab without saving.

    REAPER action 40860 = 'Close current project tab'.
    We first make sure transport is stopped, then close.
    """
    try:
        RPR.Main_OnCommand(1016, 0)   # Transport: Stop
        RPR.Main_OnCommand(40860, 0)   # Close current project tab
        p = reapy.Project()
        restored = p.name or "(untitled)"
        print(f"  Restored original project: {restored}")
    except Exception as e:
        print(f"  WARNING: Failed to close test project tab: {e}")
        print(f"  You may need to close the empty tab manually.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_test_track(name="__scythe_test__"):
    """Add a track and return its index."""
    result = tracks.add_track(name=name)
    return result["index"]


def _delete_test_track(idx):
    """Delete a track by index."""
    tracks.delete_track(track_index=idx)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_project_info():
    result = project.get_project_info()
    assert "name" in result, "Missing 'name' key"
    assert "bpm" in result, "Missing 'bpm' key"
    assert "n_tracks" in result, "Missing 'n_tracks' key"
    assert result["sample_rate"] > 0, "Invalid sample rate"


def test_transport_state():
    result = project.get_transport_state()
    assert "is_playing" in result, "Missing 'is_playing' key"
    assert "is_stopped" in result, "Missing 'is_stopped' key"
    assert "cursor_position" in result, "Missing 'cursor_position' key"


def test_cursor_position():
    project.set_cursor_position(5.0)
    moved = project.get_transport_state()["cursor_position"]
    assert abs(moved - 5.0) < 0.1, f"Cursor not at 5.0, got {moved}"
    project.set_cursor_position(0.0)


def test_track_lifecycle():
    """Create a track, modify it, then delete it."""
    n_before = project.get_project_info()["n_tracks"]

    # Create
    idx = _add_test_track("__scythe_lifecycle__")

    # Verify count
    assert project.get_project_info()["n_tracks"] == n_before + 1, "Track not added"

    # Rename
    tracks.set_track_name(track_index=idx, name="__scythe_renamed__")
    info = tracks.get_track_info(track_index=idx)
    assert info["name"] == "__scythe_renamed__", "Rename failed"

    # Volume
    tracks.set_track_volume(track_index=idx, volume_db=-6.0)
    info = tracks.get_track_info(track_index=idx)
    assert abs(info["volume_db"] - (-6.0)) < 0.5, "Volume not set"

    # Pan
    tracks.set_track_pan(track_index=idx, pan=0.5)
    info = tracks.get_track_info(track_index=idx)
    assert abs(info["pan"] - 0.5) < 0.1, "Pan not set"

    # Mute/Solo
    tracks.set_track_mute_solo(track_index=idx, mute=True)
    info = tracks.get_track_info(track_index=idx)
    assert info["muted"] is True, "Mute not set"
    tracks.set_track_mute_solo(track_index=idx, mute=False)

    # Color
    tracks.set_track_color(track_index=idx, r=255, g=0, b=0)

    # Arm
    tracks.set_track_record_arm(track_index=idx, armed=True)
    info = tracks.get_track_info(track_index=idx)
    assert info["armed"] is True, "Arm not set"
    tracks.set_track_record_arm(track_index=idx, armed=False)

    # Delete
    _delete_test_track(idx)
    assert project.get_project_info()["n_tracks"] == n_before, "Track not deleted"


def test_list_tracks():
    result = tracks.list_tracks()
    assert "n_tracks" in result, "Missing 'n_tracks'"
    assert "tracks" in result, "Missing 'tracks'"


def test_track_fx_lifecycle():
    """Add FX to a temporary track, tweak params, then clean up."""
    idx = _add_test_track("__scythe_fx_test__")

    try:
        # Add FX
        fx_result = track_fx.add_track_fx(track_index=idx, fx_name="ReaEQ")
        fx_idx = fx_result["fx_index"]

        # List FX
        fx_list = track_fx.list_track_fx(track_index=idx)
        assert fx_list["n_fx"] >= 1, "FX not listed"

        # Get params
        params = track_fx.get_track_fx_params(track_index=idx, fx_index=fx_idx)
        assert "params" in params, "Missing params"

        # Set a param (first available)
        if params["params"]:
            track_fx.set_track_fx_param(
                track_index=idx, fx_index=fx_idx, param_index=0, value=0.5
            )

        # Enable/bypass
        track_fx.set_track_fx_enabled(track_index=idx, fx_index=fx_idx, enabled=False)
        track_fx.set_track_fx_enabled(track_index=idx, fx_index=fx_idx, enabled=True)

        # Remove FX
        track_fx.remove_track_fx(track_index=idx, fx_index=fx_idx)
    finally:
        _delete_test_track(idx)


def test_send_lifecycle():
    """Create two tracks, add a send between them, then clean up."""
    src_idx = _add_test_track("__scythe_send_src__")
    dst_idx = _add_test_track("__scythe_send_dst__")

    try:
        # Create send
        send_result = sends.create_send(
            src_track_index=src_idx, dst_track_index=dst_idx
        )
        send_idx = send_result["send_index"]

        # List sends
        send_list = sends.list_track_sends(track_index=src_idx)
        assert send_list["n_sends"] >= 1, "Send not listed"

        # List receives
        recv_list = sends.list_track_receives(track_index=dst_idx)
        assert recv_list["n_receives"] >= 1, "Receive not listed"

        # Set volume/pan
        sends.set_send_volume_pan(
            track_index=src_idx, send_index=send_idx, volume_db=-3.0
        )

        # Mute/unmute
        sends.set_send_mute(track_index=src_idx, send_index=send_idx, muted=True)
        sends.set_send_mute(track_index=src_idx, send_index=send_idx, muted=False)

        # Remove send
        sends.remove_send(track_index=src_idx, send_index=send_idx)
    finally:
        # Delete in reverse order (indices shift)
        _delete_test_track(dst_idx)
        _delete_test_track(src_idx)


def test_marker_lifecycle():
    """Add a marker, list it, then delete it."""
    pos = 999.0
    result = markers.add_marker(position=pos, name="__scythe_test__")
    idx = result["index"]

    # Verify by position (names aren't readable via dist API)
    listing = markers.list_markers()
    found = any(abs(m["position"] - pos) < 0.1 for m in listing["markers"])
    assert found, "Marker not found in listing"

    markers.delete_marker_or_region(index=idx, is_region=False)


def test_region_lifecycle():
    """Add a region, list it, then delete it."""
    result = markers.add_region(start=990.0, end=995.0, name="__scythe_test__")
    idx = result["index"]

    listing = markers.list_regions()
    found = any(abs(r["position"] - 990.0) < 0.1 for r in listing["regions"])
    assert found, "Region not found in listing"

    markers.delete_marker_or_region(index=idx, is_region=True)


def test_tempo_info():
    result = tempo.get_tempo_info()
    assert "current_bpm" in result, "Missing 'current_bpm'"
    assert result["current_bpm"] > 0, "Invalid BPM"


def test_item_lifecycle():
    """Add an empty item, move it, resize it, split it, then delete."""
    idx = _add_test_track("__scythe_item_test__")

    try:
        # Add empty item
        items.add_empty_item(track_index=idx, position=1.0, length=4.0)

        # List items
        listing = items.list_items_on_track(track_index=idx)
        assert listing["n_items"] >= 1, "Item not listed"

        # Move
        items.set_item_position(track_index=idx, item_index=0, position=2.0)

        # Resize
        items.set_item_length(track_index=idx, item_index=0, length=6.0)

        # Split
        items.split_item(track_index=idx, item_index=0, position=5.0)
        listing2 = items.list_items_on_track(track_index=idx)
        assert listing2["n_items"] >= 2, "Split didn't create second item"

        # Delete both items (reverse order)
        for i in range(listing2["n_items"] - 1, -1, -1):
            items.delete_item(track_index=idx, item_index=i)
    finally:
        _delete_test_track(idx)


def test_midi_lifecycle():
    """Create MIDI item, add notes and CC, then clean up."""
    idx = _add_test_track("__scythe_midi_test__")

    try:
        # Create MIDI item
        midi.create_midi_item(track_index=idx, position=0.0, length=4.0)

        # Add note (C4, velocity 100, beat 0 to beat 1 = 0 to 960 PPQ)
        midi.add_midi_note(
            track_index=idx, item_index=0,
            pitch=60, velocity=100, start_ppq=0, end_ppq=960,
        )

        # List notes
        notes = midi.list_midi_notes(track_index=idx, item_index=0)
        assert notes["n_notes"] >= 1, "Note not listed"

        # Edit note
        midi.set_midi_note(
            track_index=idx, item_index=0, note_index=0, velocity=80
        )

        # Add CC
        midi.add_midi_cc(
            track_index=idx, item_index=0,
            cc_num=1, value=64, ppq_position=0,
        )

        # List CC
        cc_list = midi.list_midi_cc(track_index=idx, item_index=0)
        assert cc_list["n_cc_events"] >= 1, "CC not listed"

        # Delete CC then note
        midi.delete_midi_cc(track_index=idx, item_index=0, cc_index=0)
        midi.delete_midi_note(track_index=idx, item_index=0, note_index=0)

        # Delete item
        items.delete_item(track_index=idx, item_index=0)
    finally:
        _delete_test_track(idx)


def test_envelopes():
    """Create a track, list its envelopes (read-only)."""
    idx = _add_test_track("__scythe_env_test__")
    try:
        result = envelopes.list_track_envelopes(track_index=idx)
        assert "envelopes" in result, "Missing 'envelopes' key"
    finally:
        _delete_test_track(idx)


def test_time_selection():
    """Set and get time selection, then clear it."""
    time_selection.set_time_selection(start=2.0, end=8.0)
    result = time_selection.get_time_selection()
    assert abs(result["start"] - 2.0) < 0.1, f"Start not set, got {result['start']}"
    assert abs(result["end"] - 8.0) < 0.1, f"End not set, got {result['end']}"
    # Clear
    time_selection.set_time_selection(start=0.0, end=0.0)


def test_loop():
    """Toggle loop on and off."""
    time_selection.set_loop(enabled=True, start=1.0, end=5.0)
    result = time_selection.get_time_selection()
    assert result["loop_enabled"] is True, "Loop not enabled"
    time_selection.set_loop(enabled=False)


def test_ext_state():
    """Write, read, and delete an extended state key."""
    ext_state.set_ext_state(
        section="scythe_test", key="smoke", value="pass", persist=False
    )
    result = ext_state.get_ext_state(section="scythe_test", key="smoke")
    assert result["value"] == "pass", f"Got: {result['value']}"
    ext_state.delete_ext_state(section="scythe_test", key="smoke")


def test_devices():
    """List audio and MIDI devices (read-only)."""
    audio = devices.list_audio_devices()
    assert "n_inputs" in audio, "Missing 'n_inputs'"
    midi_devs = devices.list_midi_devices()
    assert "midi_inputs" in midi_devs, "Missing 'midi_inputs'"


def test_actions():
    """Look up and perform a safe action (40340 = set playback rate to 1x)."""
    result = actions.perform_action(action_id=40340)
    assert "action_id" in result, "Missing 'action_id'"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main():
    print()
    print("=" * 60)
    print("  Scythe Smoke Tests")
    print("  REAPER must be running with reapy server active")
    print("=" * 60)
    print()

    # Connection check
    try:
        p = reapy.Project()
        print(f"  Connected to REAPER: {p.name or '(untitled project)'}")
    except Exception as e:
        print(f"  FATAL: Cannot connect to REAPER: {e}")
        print("  Make sure REAPER is running and 'Activate reapy server' was run.")
        sys.exit(1)

    print()

    # Create isolated test project
    print("  Setting up test project...")
    setup_test_project()
    print()

    try:
        # Run tests in logical order
        run_test("project_info", test_project_info)
        run_test("transport_state", test_transport_state)
        run_test("cursor_position", test_cursor_position)
        run_test("list_tracks", test_list_tracks)
        run_test("track_lifecycle", test_track_lifecycle)
        run_test("track_fx_lifecycle", test_track_fx_lifecycle)
        run_test("send_lifecycle", test_send_lifecycle)
        run_test("marker_lifecycle", test_marker_lifecycle)
        run_test("region_lifecycle", test_region_lifecycle)
        run_test("tempo_info", test_tempo_info)
        run_test("item_lifecycle", test_item_lifecycle)
        run_test("midi_lifecycle", test_midi_lifecycle)
        run_test("envelopes", test_envelopes)
        run_test("time_selection", test_time_selection)
        run_test("loop", test_loop)
        run_test("ext_state", test_ext_state)
        run_test("devices", test_devices)
        run_test("actions", test_actions)
    finally:
        # Always clean up — close the test tab, restore original project
        print()
        print("  Tearing down test project...")
        teardown_test_project()

    # Summary
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = len(_results)

    print()
    print("-" * 60)
    print(f"  {passed}/{total} passed, {failed} failed")

    if failed:
        print()
        print("  Failed tests:")
        for name, ok, msg in _results:
            if not ok:
                print(f"    - {name}: {msg}")

    print("-" * 60)
    print()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
