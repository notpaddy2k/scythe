"""Take (item) FX management tools for REAPER."""

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

mcp = FastMCP("take_fx")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_take(track: reapy.Track, item_index: int) -> reapy.Take:
    """Return the active take of the item, or raise ToolError."""
    item = validate_item_index(track, item_index)
    take = item.active_take
    if take is None:
        raise ToolError(
            f"Item {item_index} on track '{track.name}' has no active take."
        )
    return take


def _validate_take_fx_index(take: reapy.Take, idx: int):
    """Validate an FX index on a take, returning the FX object."""
    n = len(take.fxs)
    if idx < 0 or idx >= n:
        raise ToolError(
            f"FX index {idx} out of range on take. "
            f"Take has {n} FX (valid: 0-{n - 1})."
        )
    return take.fxs[idx]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_take_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    item_index: Annotated[int, Field(description="Zero-based item index on the track", ge=0)],
) -> dict:
    """List all FX on the active take of a media item.

    Returns slot index, name, enabled state, and online state for every FX
    in the take's FX chain.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        take = _get_active_take(track, item_index)
        fx_list = []
        for i, fx in enumerate(take.fxs):
            fx_list.append({
                "index": i,
                "name": fx.name,
                "is_enabled": fx.is_enabled,
                "is_online": fx.is_online,
            })
        return {
            "track_index": track_index,
            "track_name": track.name,
            "item_index": item_index,
            "n_fx": len(fx_list),
            "fx": fx_list,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list take FX: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_take_fx_params(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    item_index: Annotated[int, Field(description="Zero-based item index on the track", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
) -> dict:
    """Get all parameters of a take FX plugin.

    Returns each parameter's name, normalized value (0-1), and formatted
    display string.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        take = _get_active_take(track, item_index)
        fx = _validate_take_fx_index(take, fx_index)
        params = []
        for i in range(fx.n_params):
            # Parameter name with RPR fallback
            try:
                name = fx.params[i].name
            except Exception:
                _, _, _, name, _ = RPR.TakeFX_GetParamName(
                    take.id, fx_index, i, "", 256
                )

            # Normalized value
            value = RPR.TakeFX_GetParamNormalized(take.id, fx_index, i)

            # Formatted display string with RPR fallback
            try:
                formatted = fx.params[i].formatted
            except Exception:
                _, _, _, formatted, _ = RPR.TakeFX_GetFormattedParamValue(
                    take.id, fx_index, i, "", 256
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
            "item_index": item_index,
            "fx_index": fx_index,
            "fx_name": fx.name,
            "n_params": len(params),
            "params": params,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to get take FX params: {exc}") from exc


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def add_take_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    item_index: Annotated[int, Field(description="Zero-based item index on the track", ge=0)],
    fx_name: Annotated[str, Field(description="FX plugin name to add (e.g. 'ReaEQ', 'VST: Compressor')")],
) -> dict:
    """Add an FX plugin to the active take's FX chain.

    The FX is appended to the end of the chain. Returns the new FX slot
    index, or raises an error if the plugin was not found.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        take = _get_active_take(track, item_index)
        with undo_block(f"Add FX '{fx_name}' to take on track '{track.name}'"):
            new_index = RPR.TakeFX_AddByName(take.id, fx_name, -1)
        if new_index < 0:
            raise ToolError(
                f"FX '{fx_name}' not found. Check the plugin name and ensure "
                f"it is installed."
            )
        return {
            "track_index": track_index,
            "track_name": track.name,
            "item_index": item_index,
            "fx_index": new_index,
            "fx_name": fx_name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to add take FX: {exc}") from exc


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": False,
    }
)
def remove_take_fx(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    item_index: Annotated[int, Field(description="Zero-based item index on the track", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index to remove", ge=0)],
) -> dict:
    """Remove an FX plugin from the active take's FX chain.

    WARNING: This permanently removes the FX and its settings from the chain.
    Subsequent FX indices will shift down by one.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        take = _get_active_take(track, item_index)
        fx = _validate_take_fx_index(take, fx_index)
        fx_name = fx.name
        with undo_block(f"Remove FX '{fx_name}' from take on track '{track.name}'"):
            RPR.TakeFX_Delete(take.id, fx_index)
        return {
            "track_index": track_index,
            "track_name": track.name,
            "item_index": item_index,
            "removed_fx_index": fx_index,
            "removed_fx_name": fx_name,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to remove take FX: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": False})
def set_take_fx_param(
    track_index: Annotated[int, Field(description="Zero-based track index", ge=0)],
    item_index: Annotated[int, Field(description="Zero-based item index on the track", ge=0)],
    fx_index: Annotated[int, Field(description="Zero-based FX slot index", ge=0)],
    param_index: Annotated[int, Field(description="Zero-based parameter index", ge=0)],
    value: Annotated[float, Field(description="Normalized parameter value (0.0 to 1.0)", ge=0.0, le=1.0)],
) -> dict:
    """Set a normalized parameter value on a take FX.

    The value must be between 0.0 and 1.0. Use get_take_fx_params first
    to discover available parameters and their current values.
    """
    try:
        project = get_project()
        track = validate_track_index(project, track_index)
        take = _get_active_take(track, item_index)
        fx = _validate_take_fx_index(take, fx_index)
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
            _, _, _, param_name, _ = RPR.TakeFX_GetParamName(
                take.id, fx_index, param_index, "", 256
            )

        with undo_block(
            f"Set '{param_name}' to {value:.4f} on take FX '{fx.name}' "
            f"(track '{track.name}')"
        ):
            RPR.TakeFX_SetParamNormalized(take.id, fx_index, param_index, value)

        # Read back formatted value for confirmation
        try:
            formatted = fx.params[param_index].formatted
        except Exception:
            _, _, _, formatted, _ = RPR.TakeFX_GetFormattedParamValue(
                take.id, fx_index, param_index, "", 256
            )

        return {
            "track_index": track_index,
            "track_name": track.name,
            "item_index": item_index,
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
        raise ToolError(f"Failed to set take FX parameter: {exc}") from exc
