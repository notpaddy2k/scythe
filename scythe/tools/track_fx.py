"""Track FX management tools for REAPER."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
import reapy
import reapy.reascript_api as RPR

from scythe.helpers import (
    get_project,
    validate_track_index,
    validate_fx_index,
    undo_block,
)

mcp = FastMCP("track_fx")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_track_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
) -> dict:
    """List all FX on a track.

    Returns slot index, name, enabled state, and online state for every FX
    in the track's FX chain.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx_list = []
        for i, fx in enumerate(track.fxs):
            fx_list.append({
                "index": i,
                "name": fx.name,
                "is_enabled": fx.is_enabled,
                "is_online": fx.is_online,
            })
        return {
            "track_index": track_index,
            "track_name": track.name,
            "n_fx": len(fx_list),
            "fx": fx_list,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list track FX: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_track_fx_params(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
) -> dict:
    """Get all parameters of a track FX plugin.

    Returns each parameter's name, normalized value (0-1), and formatted
    display string (e.g. "-6.0 dB", "100 Hz").
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)
        params = []
        for i in range(fx.n_params):
            # Parameter name — reapy attribute with RPR fallback
            try:
                name = fx.params[i].name
            except Exception:
                _, _, _, name, _ = RPR.TrackFX_GetParamName(
                    track.id, fx_index, i, "", 256
                )

            # Normalized value
            value = RPR.TrackFX_GetParamNormalized(track.id, fx_index, i)

            # Formatted display string — reapy attribute with RPR fallback
            try:
                formatted = fx.params[i].formatted
            except Exception:
                _, _, _, formatted, _ = RPR.TrackFX_GetFormattedParamValue(
                    track.id, fx_index, i, "", 256
                )

            params.append({
                "index": i,
                "name": name,
                "value": value,
                "formatted": formatted,
            })
        return {
            "track_index": track_index,
            "track_name": track.name,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "n_params": len(params),
            "params": params,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get FX params: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_track_fx_preset(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
) -> dict:
    """Get the current preset name and index for a track FX.

    Returns the active preset name, its index, and the total number of
    available presets.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)

        retval, _, _, preset_name, _ = RPR.TrackFX_GetPreset(
            track.id, fx_index, "", 256
        )
        preset_idx, n_presets = RPR.TrackFX_GetPresetIndex(track.id, fx_index)

        return {
            "track_index": track_index,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "preset_name": preset_name if retval else None,
            "preset_index": preset_idx,
            "n_presets": n_presets,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get FX preset: {exc}") from exc


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_track_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_name: Annotated[str, Field(description="FX plugin name to add (e.g. 'ReaEQ', 'VST: Compressor')")],
) -> dict:
    """Add an FX plugin to a track's FX chain.

    The FX is appended to the end of the chain. Returns the new FX slot
    index, or raises an error if the plugin was not found.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        with undo_block(f"Add FX '{fx_name}' to track '{track.name}'"):
            new_index = RPR.TrackFX_AddByName(track.id, fx_name, False, -1)
        if new_index < 0:
            raise ToolError(
                f"FX '{fx_name}' not found. Check the plugin name and ensure "
                f"it is installed."
            )
        return {
            "track_index": track_index,
            "track_name": track.name,
            "fx_index": new_index,
            "fx_name": fx_name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add FX: {exc}") from exc


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    }
)
def remove_track_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index to remove", ge=0)],
) -> dict:
    """Remove an FX plugin from a track's FX chain.

    WARNING: This permanently removes the FX and its settings from the chain.
    Subsequent FX indices will shift down by one.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)
        fx_name = fx.name
        with undo_block(f"Remove FX '{fx_name}' from track '{track.name}'"):
            RPR.TrackFX_Delete(track.id, fx_index)
        return {
            "track_index": track_index,
            "track_name": track.name,
            "removed_fx_index": fx_index,
            "removed_fx_name": fx_name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to remove FX: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_fx_enabled(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
    enabled: Annotated[bool, Field(description="True to enable the FX, False to bypass it")],
) -> dict:
    """Enable or bypass an FX plugin on a track."""
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)
        with undo_block(
            f"{'Enable' if enabled else 'Bypass'} FX '{fx.name}' on track '{track.name}'"
        ):
            fx.is_enabled = enabled
        return {
            "track_index": track_index,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "is_enabled": enabled,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set FX enabled state: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_fx_param(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
    param_index: Annotated[int, Field(description="Zero-based parameter index", ge=0)],
    value: Annotated[float, Field(description="Normalized parameter value (0.0 to 1.0)", ge=0.0, le=1.0)],
) -> dict:
    """Set a normalized parameter value on a track FX.

    The value must be between 0.0 and 1.0. Use get_track_fx_params first
    to discover available parameters and their current values.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)
        if param_index < 0 or param_index >= fx.n_params:
            raise ToolError(
                f"Parameter index {param_index} out of range. "
                f"FX '{fx.name}' has {fx.n_params} parameters "
                f"(valid: 0-{fx.n_params - 1})."
            )

        # Get param name for undo description
        try:
            param_name = fx.params[param_index].name
        except Exception:
            _, _, _, param_name, _ = RPR.TrackFX_GetParamName(
                track.id, fx_index, param_index, "", 256
            )

        with undo_block(
            f"Set '{param_name}' to {value:.4f} on '{fx.name}' (track '{track.name}')"
        ):
            RPR.TrackFX_SetParamNormalized(track.id, fx_index, param_index, value)

        # Read back formatted value for confirmation
        try:
            formatted = fx.params[param_index].formatted
        except Exception:
            _, _, _, formatted, _ = RPR.TrackFX_GetFormattedParamValue(
                track.id, fx_index, param_index, "", 256
            )

        return {
            "track_index": track_index,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "param_index": param_index,
            "param_name": param_name,
            "value": value,
            "formatted": formatted,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set FX parameter: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_track_fx_preset(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
    preset_name: Annotated[
        str | None,
        Field(description="Exact preset name to load. Mutually exclusive with delta."),
    ] = None,
    delta: Annotated[
        int | None,
        Field(description="Navigate presets by offset (+1 = next, -1 = previous). Mutually exclusive with preset_name."),
    ] = None,
) -> dict:
    """Set or navigate FX presets on a track.

    Provide either preset_name to load a specific preset by name, or delta
    to step through presets relative to the current one (+1 for next,
    -1 for previous). Exactly one of the two must be specified.
    """
    try:
        if preset_name is None and delta is None:
            raise ToolError(
                "Provide either 'preset_name' or 'delta', not neither."
            )
        if preset_name is not None and delta is not None:
            raise ToolError(
                "Provide either 'preset_name' or 'delta', not both."
            )

        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)

        if preset_name is not None:
            with undo_block(
                f"Set preset '{preset_name}' on '{fx.name}' (track '{track.name}')"
            ):
                ok = RPR.TrackFX_SetPreset(track.id, fx_index, preset_name)
            if not ok:
                raise ToolError(
                    f"Preset '{preset_name}' not found for FX '{fx.name}'."
                )
        else:
            with undo_block(
                f"Navigate preset by {delta:+d} on '{fx.name}' (track '{track.name}')"
            ):
                ok = RPR.TrackFX_NavigatePresets(track.id, fx_index, delta)
            if not ok:
                raise ToolError(
                    f"Failed to navigate presets by {delta:+d} on FX '{fx.name}'."
                )

        # Read back current preset state
        _, _, _, new_preset_name, _ = RPR.TrackFX_GetPreset(
            track.id, fx_index, "", 256
        )
        new_idx, n_presets = RPR.TrackFX_GetPresetIndex(track.id, fx_index)

        return {
            "track_index": track_index,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "preset_name": new_preset_name,
            "preset_index": new_idx,
            "n_presets": n_presets,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to set FX preset: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def copy_track_fx(
    src_track_index: Annotated[int, Field(description="Zero-based source track index", ge=0)],
    src_fx_index: Annotated[int, Field(description="Zero-based FX slot index on the source track", ge=0)],
    dst_track_index: Annotated[int, Field(description="Zero-based destination track index", ge=0)],
    dst_position: Annotated[
        int,
        Field(description="Position in destination FX chain (-1 to append at end)"),
    ] = -1,
) -> dict:
    """Copy an FX plugin from one track to another.

    The FX and all its parameter settings are duplicated to the destination
    track. Use dst_position=-1 to append at the end of the destination chain.
    """
    try:
        project = get_project()
        src_track = validate_track_index(project, src_track_index)
        src_fx = validate_fx_index(src_track, src_fx_index)
        dst_track = validate_track_index(project, dst_track_index)

        if dst_position >= 0:
            # Validate that dst_position is within a reasonable range
            dst_n = dst_track.n_fxs
            if dst_position > dst_n:
                raise ToolError(
                    f"Destination position {dst_position} out of range. "
                    f"Destination track '{dst_track.name}' has {dst_n} FX "
                    f"(valid: 0-{dst_n}, or -1 to append)."
                )

        fx_name = src_fx.name
        with undo_block(
            f"Copy FX '{fx_name}' from track '{src_track.name}' "
            f"to track '{dst_track.name}'"
        ):
            RPR.TrackFX_CopyToTrack(
                src_track.id, src_fx_index,
                dst_track.id, dst_position,
                False,
            )

        return {
            "src_track_index": src_track_index,
            "src_track_name": src_track.name,
            "src_fx_index": src_fx_index,
            "fx_name": fx_name,
            "dst_track_index": dst_track_index,
            "dst_track_name": dst_track.name,
            "dst_position": dst_position,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to copy FX: {exc}") from exc


# ---------------------------------------------------------------------------
# Parameter probing
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def probe_fx_param_value(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
    param_index: Annotated[int, Field(description="Zero-based parameter index", ge=0)],
    target_display: Annotated[
        str,
        Field(description="Target display string to search for (e.g. '1000 Hz', '-6.0 dB')"),
    ],
    probe_min: Annotated[
        float,
        Field(description="Minimum normalized value to probe", ge=0.0, le=1.0),
    ] = 0.0,
    probe_max: Annotated[
        float,
        Field(description="Maximum normalized value to probe", ge=0.0, le=1.0),
    ] = 1.0,
    probe_steps: Annotated[
        int,
        Field(description="Number of probe steps (higher = more precise)", ge=10, le=10000),
    ] = 1000,
) -> dict:
    """Discover the normalized value that produces a target display string.

    Probes the parameter across a range of normalized values, reading
    the formatted display at each step to find a match.  The original
    parameter value is ALWAYS restored, making this effectively read-only.

    Note: if REAPER crashes during probing the parameter may be left at
    a probed value.  This is extremely unlikely in practice.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        fx = validate_fx_index(track, fx_index)

        if param_index < 0 or param_index >= fx.n_params:
            raise ToolError(
                f"Parameter index {param_index} out of range. "
                f"FX '{fx.name}' has {fx.n_params} parameters "
                f"(valid: 0-{fx.n_params - 1})."
            )

        if probe_min >= probe_max:
            raise ToolError(
                f"probe_min ({probe_min}) must be less than "
                f"probe_max ({probe_max})."
            )

        # Save original value — reapy returns list from RPR calls
        orig_ret = RPR.TrackFX_GetParamNormalized(
            track.id, fx_index, param_index
        )
        original_value = orig_ret if isinstance(orig_ret, float) else float(orig_ret)

        def _read_display() -> str:
            """Read the current formatted display via RPR (not cached reapy)."""
            ret = RPR.TrackFX_GetFormattedParamValue(
                track.id, fx_index, param_index, "", 256
            )
            if isinstance(ret, (list, tuple)) and len(ret) >= 4:
                return str(ret[3])
            return str(ret)

        original_formatted = _read_display()

        target_lower = target_display.strip().lower()
        found_value = None
        found_display = None
        restored = False

        try:
            step_size = (probe_max - probe_min) / probe_steps
            for i in range(probe_steps + 1):
                test_val = probe_min + (i * step_size)
                test_val = max(0.0, min(1.0, test_val))

                RPR.TrackFX_SetParamNormalized(
                    track.id, fx_index, param_index, test_val
                )

                formatted = _read_display()

                if formatted.strip().lower() == target_lower:
                    found_value = test_val
                    found_display = formatted
                    break
        finally:
            # ALWAYS restore original value
            RPR.TrackFX_SetParamNormalized(
                track.id, fx_index, param_index, original_value
            )
            restored = True

        return {
            "found": found_value is not None,
            "internal_value": found_value,
            "matched_display": found_display,
            "target_display": target_display,
            "original_value": original_value,
            "original_display": original_formatted,
            "restored": restored,
            "probe_steps": probe_steps,
            "probe_min": probe_min,
            "probe_max": probe_max,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to probe FX parameter: {exc}") from exc
