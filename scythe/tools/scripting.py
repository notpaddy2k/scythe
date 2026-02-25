"""Run Lua or EEL scripts inside REAPER from the MCP."""

from __future__ import annotations

import os
import tempfile
from typing import Annotated

from pydantic import Field
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from scythe.helpers import get_project

mcp = FastMCP("scripting")

# ExtState section used for script ↔ MCP communication
_EXTSTATE_SECTION = "scythe_script_ipc"
_EXTSTATE_KEY = "result"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_ipc() -> None:
    """Clear the IPC mailbox before a script run."""
    import reapy.reascript_api as RPR
    RPR.DeleteExtState(_EXTSTATE_SECTION, _EXTSTATE_KEY, False)


def _read_ipc() -> str:
    """Read and clear the IPC mailbox after a script run."""
    import reapy.reascript_api as RPR
    result = RPR.GetExtState(_EXTSTATE_SECTION, _EXTSTATE_KEY)
    if isinstance(result, (list, tuple)):
        result = result[-1] if result else ""
    RPR.DeleteExtState(_EXTSTATE_SECTION, _EXTSTATE_KEY, False)
    return str(result)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def run_lua_script(
    script: Annotated[
        str,
        Field(description="Lua source code to execute inside REAPER"),
    ],
    return_result: Annotated[
        bool,
        Field(
            description=(
                "If true, the script should write its result via "
                "reaper.SetExtState('scythe_script_ipc', 'result', value, false) "
                "and the tool will return that value. Defaults to false."
            ),
        ),
    ] = False,
) -> dict:
    """Run a Lua script inside REAPER.

    The script has full access to the REAPER Lua API (reaper.*, gfx.*, etc.).
    It runs synchronously on REAPER's main thread.

    To return data back to the MCP, set return_result=true and call
    ``reaper.SetExtState('scythe_script_ipc', 'result', your_string, false)``
    at the end of your script. The tool will read and return that value.

    WARNING: This is a powerful escape hatch. The script can modify the
    project, change settings, and access the filesystem. Use with care.
    """
    try:
        get_project()
        import reapy.reascript_api as RPR

        # Write script to a temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".lua", delete=False, encoding="utf-8",
        )
        try:
            tmp.write(script)
            tmp.close()
            script_path = tmp.name

            # Clear IPC mailbox
            if return_result:
                _clear_ipc()

            # Register the script as an action (section 0 = main)
            cmd_id = RPR.AddRemoveReaScript(True, 0, script_path, True)
            if isinstance(cmd_id, (list, tuple)):
                cmd_id = cmd_id[0] if cmd_id else 0
            cmd_id = int(cmd_id)

            if cmd_id == 0:
                raise ToolError(
                    "REAPER failed to register the script. "
                    "Check that Lua scripting is enabled."
                )

            # Execute
            RPR.Main_OnCommand(cmd_id, 0)

            # Unregister
            RPR.AddRemoveReaScript(False, 0, script_path, True)

            # Read result if requested
            result_value = None
            if return_result:
                result_value = _read_ipc()

            resp: dict = {"executed": True, "command_id": cmd_id}
            if result_value is not None:
                resp["result"] = result_value
            return resp
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to run Lua script: {exc}") from exc


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def run_eel_script(
    script: Annotated[
        str,
        Field(description="EEL2 source code to execute inside REAPER"),
    ],
    return_result: Annotated[
        bool,
        Field(
            description=(
                "If true, the script should write its result via "
                "extension_api('SetExtState', 'scythe_script_ipc', 'result', value, 0) "
                "and the tool will return that value. Defaults to false."
            ),
        ),
    ] = False,
) -> dict:
    """Run an EEL2 script inside REAPER.

    EEL2 is REAPER's built-in scripting language with no external
    dependencies. It runs synchronously on REAPER's main thread.

    To return data back to the MCP, set return_result=true and use the
    appropriate ExtState call at the end of your script.

    WARNING: This is a powerful escape hatch. The script can modify the
    project, change settings, and access the filesystem. Use with care.
    """
    try:
        get_project()
        import reapy.reascript_api as RPR

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".eel", delete=False, encoding="utf-8",
        )
        try:
            tmp.write(script)
            tmp.close()
            script_path = tmp.name

            if return_result:
                _clear_ipc()

            cmd_id = RPR.AddRemoveReaScript(True, 0, script_path, True)
            if isinstance(cmd_id, (list, tuple)):
                cmd_id = cmd_id[0] if cmd_id else 0
            cmd_id = int(cmd_id)

            if cmd_id == 0:
                raise ToolError(
                    "REAPER failed to register the EEL script. "
                    "Check that EEL scripting is enabled."
                )

            RPR.Main_OnCommand(cmd_id, 0)
            RPR.AddRemoveReaScript(False, 0, script_path, True)

            result_value = None
            if return_result:
                result_value = _read_ipc()

            resp: dict = {"executed": True, "command_id": cmd_id}
            if result_value is not None:
                resp["result"] = result_value
            return resp
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Failed to run EEL script: {exc}") from exc
