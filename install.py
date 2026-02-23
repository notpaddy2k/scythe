#!/usr/bin/env python3
"""
install.py — Cross-platform installer for reaper-mcp
Works on macOS, Linux, and Windows.

The venv is stored in a local cache directory (NOT inside the repo)
so it never gets synced via Google Drive / iCloud / OneDrive.

Usage:
    python install.py
    python install.py --dry-run
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def header(text: str):
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")

def ok(text: str):
    print(f"  ✅ {text}")

def warn(text: str):
    print(f"  ⚠️  {text}")

def info(text: str):
    print(f"  ℹ️  {text}")

def fail(text: str):
    print(f"  ❌ {text}")
    sys.exit(1)


# ── Platform detection ────────────────────────────────────────────────────────

def get_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac"
    elif system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    else:
        fail(f"Unsupported platform: {system}")


def get_claude_config_path() -> Path:
    p = get_platform()
    if p == "mac":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif p == "windows":
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    else:  # linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_local_venv_dir(script_dir: Path) -> Path:
    """
    Return a local (non-synced) directory to store the venv.

    Uses the platform cache dir so the venv never ends up inside
    Google Drive / iCloud / OneDrive.

    Mac:     ~/Library/Caches/reaper-mcp-<hash>
    Windows: %LOCALAPPDATA%/reaper-mcp-<hash>
    Linux:   ~/.cache/reaper-mcp-<hash>
    """
    p = get_platform()
    import hashlib
    dir_hash = hashlib.md5(str(script_dir).encode()).hexdigest()[:8]
    name = f"reaper-mcp-{dir_hash}"

    if p == "mac":
        return Path.home() / "Library" / "Caches" / name
    elif p == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local_app_data) / name
    else:  # linux
        xdg_cache = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
        return Path(xdg_cache) / name


# ── uv ────────────────────────────────────────────────────────────────────────

def ensure_uv() -> Path:
    header("Checking uv")
    uv = shutil.which("uv")
    if uv:
        ok(f"uv found: {uv}")
        return Path(uv)

    warn("uv not found — installing...")
    p = get_platform()
    try:
        if p == "windows":
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "ByPass", "-c",
                 "irm https://astral.sh/uv/install.ps1 | iex"],
                check=True
            )
            user_path = subprocess.check_output(
                ["powershell", "-c", "[System.Environment]::GetEnvironmentVariable('PATH','User')"],
                text=True
            ).strip()
            os.environ["PATH"] = user_path + ";" + os.environ.get("PATH", "")
        else:
            subprocess.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True, check=True
            )
            local_bin = Path.home() / ".local" / "bin"
            os.environ["PATH"] = str(local_bin) + ":" + os.environ.get("PATH", "")
    except subprocess.CalledProcessError:
        fail("Failed to install uv. Install manually: https://docs.astral.sh/uv/getting-started/installation/")

    uv = shutil.which("uv")
    if not uv:
        fail("uv installed but not found in PATH. Restart your terminal and re-run.")
    ok(f"uv installed: {uv}")
    return Path(uv)


# ── Dependencies ──────────────────────────────────────────────────────────────

def install_dependencies(script_dir: Path, venv_dir: Path, dry_run: bool):
    header("Installing Python dependencies")
    info(f"Venv location: {venv_dir}")

    if dry_run:
        info(f"DRY RUN: would run `uv sync` with venv at {venv_dir}")
        return

    venv_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["uv", "sync", "--project", str(script_dir)],
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv_dir)},
        check=True
    )
    ok("Dependencies installed")


# ── reapy check ───────────────────────────────────────────────────────────────

def check_reapy(venv_dir: Path, dry_run: bool):
    header("Checking reapy connection to REAPER")

    if dry_run:
        info("DRY RUN: would test reapy connection to REAPER")
        return

    # Find the python binary inside the venv
    p = get_platform()
    if p == "windows":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        warn(f"Venv python not found at {venv_python}")
        warn("Run the installer again or check the venv directory.")
        return

    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import reapy; p = reapy.Project(); print(p.name)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            project_name = result.stdout.strip() or "(untitled)"
            ok(f"reapy connected — current project: {project_name}")
        else:
            warn("reapy could not connect to REAPER.")
            info("This is OK if REAPER isn't running right now.")
            info("To set up reapy in REAPER:")
            info('  1. pip install python-reapy')
            info('  2. python -c "import reapy; reapy.configure_reaper()"')
            info("  3. Restart REAPER")
            info('  4. Verify: python -c "import reapy; print(reapy.Project().name)"')
    except subprocess.TimeoutExpired:
        warn("reapy connection timed out (REAPER may not be running).")
        info("Start REAPER and ensure the reapy extension is enabled.")
    except FileNotFoundError:
        warn(f"Python not found at: {venv_python}")


# ── Claude Desktop config ─────────────────────────────────────────────────────

def configure_claude(script_dir: Path, venv_dir: Path, uv_path: Path, dry_run: bool):
    header("Configuring Claude Desktop")

    config_file = get_claude_config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)

    new_entry = {
        "command": str(uv_path),
        "args": [
            "--directory", str(script_dir),
            "run",
            "python", "-m", "reaper_mcp"
        ],
        "env": {
            "UV_PROJECT_ENVIRONMENT": str(venv_dir)
        }
    }

    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
    else:
        config = {}

    config.setdefault("mcpServers", {})
    existing = config["mcpServers"].get("reaper_mcp")

    if existing == new_entry:
        ok("Claude config already up to date")
        return

    config["mcpServers"]["reaper_mcp"] = new_entry

    if dry_run:
        info(f"DRY RUN: would write to {config_file}:")
        print(json.dumps({"mcpServers": {"reaper_mcp": new_entry}}, indent=2))
        return

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    ok(f"Config written: {config_file}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Install reaper-mcp and configure Claude Desktop"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()

    print("\n🎛️  reaper-mcp installer")
    print(f"   Platform: {platform.system()} {platform.machine()}")
    if args.dry_run:
        print("   Mode: DRY RUN (no changes will be made)")

    script_dir = Path(__file__).parent.resolve()
    venv_dir = get_local_venv_dir(script_dir)

    uv_path = ensure_uv()
    install_dependencies(script_dir, venv_dir, args.dry_run)
    check_reapy(venv_dir, args.dry_run)
    configure_claude(script_dir, venv_dir, uv_path, args.dry_run)

    header("Done")
    ok("Restart Claude Desktop to connect.")
    if not args.dry_run:
        print()
        info("Test it by asking Claude: 'what tracks are in my REAPER project?'")
        info(f"Venv stored at: {venv_dir}")
    print()


if __name__ == "__main__":
    main()
