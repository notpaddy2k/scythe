"""Entry point for Scythe MCP server.

Works both as ``python -m scythe`` (when pip-installed) and when run
directly by Claude Desktop from an extracted .mcpb extension.
"""

import os
import subprocess
import sys
import time

# When launched from a .mcpb extension, the package isn't pip-installed,
# so we add the parent directory to sys.path so "from scythe.server ..."
# can resolve.
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# Auto-install missing dependencies on first run (.mcpb doesn't pip install).
# Uses --user to avoid permission errors and a lock file to prevent
# concurrent installs when Claude Desktop launches multiple instances.
_DEPS = {"fastmcp": "fastmcp", "reapy": "python-reapy"}
_LOCK = os.path.join(_parent, ".installing")


def _ensure_deps() -> None:
    missing = []
    for import_name, pip_name in _DEPS.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return

    # Simple lock: if another instance is already installing, wait for it.
    if os.path.exists(_LOCK):
        for _ in range(60):  # wait up to 60s
            time.sleep(1)
            if not os.path.exists(_LOCK):
                break
        # Re-check after waiting — other instance may have installed them.
        still_missing = []
        for import_name, pip_name in _DEPS.items():
            try:
                __import__(import_name)
            except ImportError:
                still_missing.append(pip_name)
        if not still_missing:
            return
        missing = still_missing

    # Acquire lock
    try:
        with open(_LOCK, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass  # non-critical, proceed anyway

    try:
        print(f"Scythe: installing dependencies ({', '.join(missing)})...", file=sys.stderr)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", "--quiet", *missing],
            timeout=120,
        )
    except subprocess.CalledProcessError:
        # Retry once without --quiet for better error visibility
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user", *missing],
                timeout=120,
            )
        except Exception as e:
            print(
                f"Scythe: failed to install dependencies. "
                f"Run manually: pip install {' '.join(missing)}\n{e}",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception as e:
        print(
            f"Scythe: failed to install dependencies. "
            f"Run manually: pip install {' '.join(missing)}\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        # Release lock
        try:
            os.remove(_LOCK)
        except OSError:
            pass


_ensure_deps()

from scythe.server import mcp  # noqa: E402


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
