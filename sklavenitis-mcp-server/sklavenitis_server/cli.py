"""CLI entry point."""

import asyncio
import sys


def main() -> None:
    """Main CLI entry point."""
    from .server import main as server_main

    try:
        asyncio.run(server_main())
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

