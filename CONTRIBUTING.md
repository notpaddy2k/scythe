# Contributing to Scythe

Thanks for your interest in making Scythe better! Here's how to get started.

## Ways to contribute

### Tools

Tools are Python files in `scythe/tools/`. Each file is a domain module with its own `FastMCP` sub-server that gets mounted by `scythe/server.py`.

**Adding a tool to an existing domain:**

1. Open the relevant file in `scythe/tools/` (e.g., `tracks.py` for track operations)
2. Add your tool function with the `@mcp.tool()` decorator
3. Use helpers from `scythe/helpers.py` — `get_project()`, `validate_track_index()`, `undo_block()`, etc.
4. Return a dict (FastMCP handles serialization)

```python
@mcp.tool(annotations={"readOnlyHint": True})
def my_new_tool(track_index: Annotated[int, Field(description="Zero-based track index", ge=0)]) -> dict:
    """Short description of what this tool does."""
    p = get_project()
    track = validate_track_index(p, track_index)
    return {"result": "some_value"}
```

**Adding a new domain:**

1. Create a new file in `scythe/tools/` (e.g., `my_domain.py`)
2. Create a `FastMCP` sub-server: `mcp = FastMCP("my_domain")`
3. Add your tools
4. Mount it in `scythe/server.py`: `mcp.mount(my_domain.mcp)`

### Skills

Skills are Markdown files in `skills/` that provide guided workflows for common production tasks. They show up as slash commands in Claude Code (e.g., `/scythe:mix`).

### Bug reports and feature requests

[Open an issue](https://github.com/notpaddy2k/reaper-mcp/issues) with:
- What you expected to happen
- What actually happened
- Your OS, Python version, and REAPER version

## Development setup

1. Clone the repo and install in editable mode:

```bash
git clone https://github.com/notpaddy2k/reaper-mcp.git
cd reaper-mcp
pip install -e .
```

2. Make sure REAPER is running with the reapy server active (see [README](README.md#prerequisites))

3. Test your changes:

```bash
python -c "import reapy; print(reapy.Project().name)"
python -m scythe
```

## Guidelines

- **Keep tools focused** — one tool does one thing
- **Use `undo_block()`** for any tool that modifies the project
- **Use `ToolError`** for user-facing errors (not raw exceptions)
- **Accept dB for volume** — convert internally with `db_to_linear()` / `linear_to_db()`
- **Validate inputs** — use the `validate_*` helpers to check track/item/FX indices
- **Add annotations** — mark read-only tools with `readOnlyHint: True`, destructive tools with `destructiveHint: True`

## Pull requests

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Test with REAPER open to verify tools work
4. Open a PR with a short description of what you changed and why

We review PRs as they come in. Small, focused PRs are easiest to review and merge.
