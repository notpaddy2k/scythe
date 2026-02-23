"""Entry point for ``python -m reaper_mcp``."""

from reaper_mcp.server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
