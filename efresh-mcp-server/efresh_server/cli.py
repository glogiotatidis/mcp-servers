"""Command-line interface for E-Fresh MCP Server."""

import argparse
import asyncio
import sys


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="E-Fresh MCP Server - Interact with e-fresh.gr grocery store"
    )
    parser.add_argument(
        "--mode",
        choices=["stdio", "http"],
        default="stdio",
        help="Server mode: stdio (for MCP clients) or http (REST API)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="HTTP server host (only for http mode, default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP server port (only for http mode, default: 8000)",
    )

    args = parser.parse_args()

    if args.mode == "stdio":
        # Run MCP server via stdio
        from .server import main as server_main

        asyncio.run(server_main())
    elif args.mode == "http":
        # Run HTTP server
        from .http_server import run_http_server

        print(f"Starting E-Fresh HTTP Server on {args.host}:{args.port}")
        print(f"API documentation available at http://{args.host}:{args.port}/docs")
        run_http_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
