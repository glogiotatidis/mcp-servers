"""CLI entry point for Skroutz MCP server."""

import argparse
import asyncio


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Skroutz MCP Server")
    parser.add_argument(
        "--mode",
        choices=["stdio", "http"],
        default="stdio",
        help="Server mode: stdio (for MCP protocol) or http (for REST API)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (HTTP mode only, default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (HTTP mode only, default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable hot reloading (HTTP mode only, watches for file changes)",
    )

    args = parser.parse_args()

    if args.mode == "http":
        from .http_server import run_http_server
        run_http_server(host=args.host, port=args.port, reload=args.reload)
    else:
        from .server import main as server_main
        asyncio.run(server_main())


if __name__ == "__main__":
    main()
