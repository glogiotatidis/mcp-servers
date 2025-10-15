"""SSE server for Skroutz MCP Server compatible with Home Assistant."""

import asyncio
import logging
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Resource, Tool, TextContent
from pydantic import AnyUrl

from .auth import AuthManager
from .skroutz_client_cffi import SkroutzClientCffi
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skroutz-sse-server")

# Create FastAPI app
app = FastAPI(
    title="Skroutz MCP SSE Server",
    description="SSE endpoint for Home Assistant MCP integration",
    version="0.1.0",
)

# Global state
auth_manager: Optional[AuthManager] = None
skroutz_client: Optional[SkroutzClientCffi] = None
mcp_server: Optional[Server] = None


def initialize():
    """Initialize the MCP server and clients."""
    global auth_manager, skroutz_client, mcp_server

    if mcp_server is not None:
        return

    logger.info("Initializing Skroutz MCP SSE Server...")

    # Initialize auth and client
    auth_manager = AuthManager()
    skroutz_client = SkroutzClientCffi(auth_manager)

    # Load credentials
    email = os.environ.get("SKROUTZ_EMAIL")
    password = os.environ.get("SKROUTZ_PASSWORD")

    if email and password:
        credentials = AuthCredentials(email=email, password=password)
        logger.info(f"Credentials loaded from environment for: {email}")
        # Auto-login
        try:
            skroutz_client.login(credentials)
            logger.info("Auto-login successful")
        except Exception as e:
            logger.warning(f"Auto-login failed: {e}")
    else:
        logger.warning("No credentials in environment variables")

    # Create MCP server instance
    mcp_server = Server("skroutz-mcp-server")

    # Register MCP handlers
    @mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available MCP tools."""
        return [
            Tool(
                name="skroutz_search_products",
                description="Search for products on Skroutz.gr",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="skroutz_get_cart",
                description="Get shopping cart contents with prices",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="skroutz_add_to_cart",
                description="Add a product to cart",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "Product URL or ID"},
                        "quantity": {"type": "integer", "description": "Quantity", "default": 1},
                    },
                    "required": ["product_id"],
                },
            ),
        ]

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle MCP tool calls."""
        try:
            if name == "skroutz_search_products":
                products = skroutz_client.search_products(arguments["query"])
                result = f"Found {len(products)} products:\n\n"
                for i, p in enumerate(products[:10], 1):
                    result += f"{i}. {p.name} - €{p.price}\n"
                return [TextContent(type="text", text=result)]

            elif name == "skroutz_get_cart":
                cart = skroutz_client.get_cart()
                result = f"Cart ({cart.item_count} items):\n\n"
                for item in cart.items:
                    result += f"- {item.product.name} x{item.quantity} = €{item.subtotal}\n"
                result += f"\nTotal: €{cart.total}"
                return [TextContent(type="text", text=result)]

            elif name == "skroutz_add_to_cart":
                details = skroutz_client.get_product_details_for_cart(arguments["product_id"])
                if details and details.get('product_id'):
                    success = skroutz_client.add_to_cart(
                        sku_id=details.get('sku_id', arguments["product_id"]),
                        product_id=details['product_id'],
                        shop_id=details['shop_id'],
                        price=details['price'],
                        quantity=arguments.get("quantity", 1)
                    )
                    msg = "Added to cart successfully" if success else "Failed to add to cart"
                    return [TextContent(type="text", text=msg)]
                return [TextContent(type="text", text="Could not extract product details")]

            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Tool error: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    initialize()


@app.get("/")
async def root():
    """Root endpoint with SSE information."""
    return {
        "name": "Skroutz MCP SSE Server",
        "version": "0.1.0",
        "transport": "SSE (Server-Sent Events)",
        "mcp_endpoint": "/sse",
        "home_assistant_compatible": True,
        "note": "For full MCP protocol support with Home Assistant, use mcp-proxy",
        "mcp_proxy_command": "mcp-proxy --stdio 'python -m skroutz_server' --port 8080",
        "endpoints": {
            "sse": "GET /sse - SSE endpoint for MCP protocol",
            "health": "GET /health - Health check"
        }
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "authenticated": auth_manager.is_authenticated() if auth_manager else False,
        "mcp_server": "initialized" if mcp_server else "not_initialized"
    }


@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE endpoint for MCP protocol (Home Assistant compatible).

    This is a simplified SSE endpoint. For full MCP protocol support with
    bidirectional communication, use mcp-proxy tool.
    """

    async def event_generator():
        """Generate SSE events."""
        try:
            logger.info("SSE client connected")

            # Send server info
            info = {
                "jsonrpc": "2.0",
                "method": "serverInfo",
                "params": {
                    "name": "skroutz-mcp-server",
                    "version": "0.1.0"
                }
            }
            yield f"event: message\ndata: {json.dumps(info)}\n\n"

            # Keep alive
            counter = 0
            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected")
                    break

                counter += 1
                # Send keepalive every 30 seconds
                yield f": keepalive {counter}\n\n"
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("SSE cancelled")
        except Exception as e:
            logger.error(f"SSE error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


def run_sse_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the SSE server."""
    import uvicorn

    logger.info(f"Starting SSE server on {host}:{port}")
    logger.info("SSE endpoint: http://{host}:{port}/sse")
    logger.info("For Home Assistant: Add MCP integration with this SSE URL")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_sse_server()

