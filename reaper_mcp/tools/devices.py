"""Audio and MIDI device information."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from reaper_mcp.helpers import get_project

mcp = FastMCP("devices")


# ---------------------------------------------------------------------------
# Device query tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_audio_devices() -> dict:
    """Get audio device information including input/output counts and latency.

    Returns the number of audio inputs and outputs available, plus the
    current input and output latency in samples.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        n_inputs = RPR.GetNumAudioInputs()
        n_outputs = RPR.GetNumAudioOutputs()
        input_latency, output_latency = RPR.GetInputOutputLatency(0, 0)
        return {
            "n_inputs": n_inputs,
            "n_outputs": n_outputs,
            "input_latency_samples": input_latency,
            "output_latency_samples": output_latency,
        }
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list audio devices: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_midi_devices() -> dict:
    """List available MIDI input and output devices.

    Returns device index and name for each MIDI input and output currently
    visible to REAPER.
    """
    try:
        get_project()  # ensure REAPER is reachable
        import reapy.reascript_api as RPR

        midi_inputs = []
        n_midi_inputs = RPR.GetNumMIDIInputs()
        for i in range(n_midi_inputs):
            retval, _dev_idx, name, _name_sz = RPR.GetMIDIInputName(i, "", 512)
            if retval:
                midi_inputs.append({"index": i, "name": name})

        midi_outputs = []
        n_midi_outputs = RPR.GetNumMIDIOutputs()
        for i in range(n_midi_outputs):
            retval, _dev_idx, name, _name_sz = RPR.GetMIDIOutputName(i, "", 512)
            if retval:
                midi_outputs.append({"index": i, "name": name})

        return {"midi_inputs": midi_inputs, "midi_outputs": midi_outputs}
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to list MIDI devices: {exc}") from exc
