# reaper-mcp

> Give Claude full control of your REAPER DAW — play, record, mix, edit MIDI, automate, render, and more.

82 tools across 16 domains. Works with Claude Desktop and Claude Code.

Built with [FastMCP 3.x](https://gofastmcp.com/) and [reapy](https://github.com/RomeoDespwortes/reapy).

---

## What can it do?

Ask Claude things like:

- *"Add a new track called Bass and set it to -6 dB"*
- *"List all the FX on track 1 and show me their parameter values"*
- *"Create a 4-bar MIDI pattern with a C minor chord progression"*
- *"Add a marker at 30 seconds called Chorus"*
- *"Set track 3 automation to write mode and add volume envelope points"*
- *"Mute tracks 4 through 6 and solo track 1"*
- *"Render the project with the current settings"*

### Full tool coverage

| Domain | Tools | What you can do |
|--------|:-----:|-----------------|
| **Project & Transport** | 8 | Get project info, play/stop/pause/record, move cursor, save |
| **Tracks** | 10 | List/add/delete tracks, volume, pan, mute, solo, arm, color |
| **Track FX** | 9 | Add/remove FX, tweak parameters, browse presets, copy FX chains |
| **Take FX** | 5 | Same as track FX but for individual item takes |
| **Sends & Receives** | 6 | Create routing, adjust send levels, mute sends |
| **Markers & Regions** | 6 | Drop markers, create regions, navigate by marker |
| **Tempo** | 4 | Read/write tempo markers, change time signatures |
| **Media Items** | 7 | Add/delete/move/split items on the timeline |
| **MIDI** | 8 | Create MIDI items, add/edit/delete notes and CC events |
| **Envelopes** | 6 | Add automation points, set modes (read/write/touch/latch) |
| **Time Selection** | 3 | Set time selection, toggle loop on/off |
| **Actions** | 3 | Run *any* REAPER action by ID or name (escape hatch) |
| **Extended State** | 3 | Persistent key-value storage between sessions |
| **Devices** | 2 | List audio and MIDI hardware |
| **Render** | 2 | Insert media files, render/bounce the project |

---

## Quick Start

### 1. Set up reapy in REAPER (one time only)

You need REAPER running with reapy's bridge enabled so Claude can talk to it.

```bash
pip install python-reapy
python -c "import reapy; reapy.configure_reaper()"
```

Restart REAPER, then verify it works:

```bash
python -c "import reapy; print(reapy.Project().name)"
```

You should see your project name (or an empty string for an untitled project).

### 2. Install the MCP server

Pick whichever method matches your setup:

#### Claude Desktop (one-click)

Download `reaper-mcp.mcpb` from [Releases](https://github.com/notpaddy2k/reaper-mcp/releases) and double-click it. Done.

Python dependencies are handled automatically via [uv](https://docs.astral.sh/uv/).

#### Claude Code (plugin)

```
/plugin marketplace add notpaddy2k/reaper-mcp
/plugin install reaper-mcp
```

The MCP server registers automatically.

#### Manual

```bash
git clone https://github.com/notpaddy2k/reaper-mcp.git
cd reaper-mcp
pip install -e .
```

Then add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "reaper_mcp": {
      "command": "python",
      "args": ["-m", "reaper_mcp"]
    }
  }
}
```

### 3. Start using it

Open REAPER, restart Claude Desktop (or Claude Code), and start asking Claude to control your session.

---

## Requirements

- [REAPER](https://www.reaper.fm/) (any recent version)
- Python 3.12+
- [reapy](https://github.com/RomeoDespwortes/reapy) 0.10.0+

---

## How it works

Each tool maps to REAPER's API via reapy. The server uses FastMCP's `mount()` pattern — 16 domain modules composed into one server:

```
reaper_mcp/
├── server.py            # Mounts all 16 domain sub-servers
├── helpers.py           # Connection, dB conversion, validation
└── tools/
    ├── project.py       # Project info & transport
    ├── tracks.py        # Track management
    ├── track_fx.py      # Track FX chain
    ├── take_fx.py       # Take FX chain
    ├── sends.py         # Routing (sends & receives)
    ├── markers.py       # Markers & regions
    ├── tempo.py         # Tempo & time signatures
    ├── items.py         # Media items
    ├── midi.py          # MIDI notes & CC
    ├── envelopes.py     # Automation envelopes
    ├── time_selection.py# Time selection & loop
    ├── actions.py       # Action escape hatch
    ├── ext_state.py     # Key-value storage
    ├── devices.py       # Audio & MIDI devices
    └── render.py        # Rendering & media import
```

The **Actions** tools (`perform_action`, `perform_named_action`) are an escape hatch — they can run *any* REAPER command, even ones not wrapped by the other 79 tools.

---

## Contributing

PRs welcome! Two ways to contribute:

- **Tools** — Python files in `reaper_mcp/tools/`. Add new tools or improve existing ones.
- **Skills** — Markdown files in `skills/`. Add guided workflows (coming soon).

---

## License

MIT
