"""REAPER MCP Server — compose all domain tool modules."""

from __future__ import annotations

from fastmcp import FastMCP

from reaper_mcp.tools import (
    actions,
    devices,
    envelopes,
    ext_state,
    items,
    markers,
    midi,
    project,
    render,
    sends,
    take_fx,
    tempo,
    time_selection,
    track_fx,
    tracks,
)

mcp = FastMCP("reaper_mcp")

# Mount every domain sub-server
mcp.mount(project.mcp)
mcp.mount(tracks.mcp)
mcp.mount(track_fx.mcp)
mcp.mount(take_fx.mcp)
mcp.mount(sends.mcp)
mcp.mount(markers.mcp)
mcp.mount(tempo.mcp)
mcp.mount(items.mcp)
mcp.mount(midi.mcp)
mcp.mount(envelopes.mcp)
mcp.mount(time_selection.mcp)
mcp.mount(actions.mcp)
mcp.mount(ext_state.mcp)
mcp.mount(devices.mcp)
mcp.mount(render.mcp)
