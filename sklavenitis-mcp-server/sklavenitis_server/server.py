"""MCP Server for Sklavenitis.gr grocery store."""

import asyncio
import logging
import os
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import AnyUrl

from .auth import AuthManager
from .sklavenitis_client import SklavenitisClient
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sklavenitis-mcp-server")

# Initialize server
app = Server("sklavenitis-mcp-server")

# Global state
auth_manager: AuthManager
sklavenitis_client: SklavenitisClient
credentials: Optional[AuthCredentials] = None


async def ensure_authenticated() -> bool:
    """Ensure the client is authenticated, auto-login if credentials are available."""
    if auth_manager.is_authenticated():
        return True

    # Try to auto-login with stored credentials
    if credentials:
        try:
            logger.info("Auto-logging in with configured credentials...")
            success = await sklavenitis_client.login(credentials)
            if success:
                logger.info("Auto-login successful")
                return True
            else:
                logger.warning("Auto-login failed")
        except Exception as e:
            logger.error(f"Auto-login error: {e}")

    return False


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    resources = []

    # If authenticated, provide cart and orders as resources
    if auth_manager.is_authenticated():
        resources.extend(
            [
                Resource(
                    uri=AnyUrl("sklavenitis://cart"),
                    name="Shopping Cart",
                    mimeType="application/json",
                    description="Current shopping cart contents",
                ),
                Resource(
                    uri=AnyUrl("sklavenitis://orders"),
                    name="Orders",
                    mimeType="application/json",
                    description="User's orders",
                ),
            ]
        )

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read a resource by URI."""
    uri_str = str(uri)

    if uri_str == "sklavenitis://cart":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        cart = sklavenitis_client.get_cart()
        return cart.model_dump_json(indent=2)

    elif uri_str == "sklavenitis://orders":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        orders = sklavenitis_client.get_orders()
        result = [order.model_dump() for order in orders]
        import json

        return json.dumps(result, indent=2, default=str)

    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="sklavenitis_login",
            description="Authenticate with sklavenitis.gr. Uses credentials from environment (SKLAVENITIS_EMAIL, SKLAVENITIS_PASSWORD) if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "User email address (optional if SKLAVENITIS_EMAIL is configured)",
                    },
                    "password": {
                        "type": "string",
                        "description": "User password (optional if SKLAVENITIS_PASSWORD is configured)",
                    },
                },
            },
        ),
        Tool(
            name="sklavenitis_logout",
            description="Logout from sklavenitis.gr and clear session",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sklavenitis_search_products",
            description="Search for products by name or EAN/barcode",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product name or search term",
                    },
                    "ean": {
                        "type": "string",
                        "description": "EAN/barcode for exact match (optional)",
                    },
                },
            },
        ),
        Tool(
            name="sklavenitis_add_to_cart",
            description="Add a product to the shopping cart",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID to add to cart",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="sklavenitis_remove_from_cart",
            description="Remove a product from the shopping cart",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID to remove from cart",
                    },
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="sklavenitis_update_cart_quantity",
            description="Update the quantity of a product in the shopping cart",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID to update",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "New quantity to set",
                    },
                },
                "required": ["product_id", "quantity"],
            },
        ),
        Tool(
            name="sklavenitis_get_cart",
            description="Get current shopping cart contents with all items and total",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sklavenitis_get_orders",
            description="Get user's orders (current and/or past orders)",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_history": {
                        "type": "boolean",
                        "description": "Include past orders (default: true)",
                        "default": True,
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "sklavenitis_login":
            # Use provided credentials or fall back to environment credentials
            email = arguments.get("email")
            password = arguments.get("password")

            # If credentials not provided, use environment credentials
            if not email or not password:
                if credentials:
                    email = credentials.email if not email else email
                    password = credentials.password if not password else password
                else:
                    return [
                        TextContent(
                            type="text",
                            text="Error: No credentials provided and SKLAVENITIS_EMAIL/SKLAVENITIS_PASSWORD not configured.",
                        )
                    ]

            login_credentials = AuthCredentials(email=email, password=password)
            success = await sklavenitis_client.login(login_credentials)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully logged in as {email}",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text="Login failed. Please check your credentials.",
                    )
                ]

        elif name == "sklavenitis_logout":
            sklavenitis_client.logout()
            return [TextContent(type="text", text="Successfully logged out")]

        elif name == "sklavenitis_search_products":
            query = arguments.get("query")
            ean = arguments.get("ean")

            products = sklavenitis_client.search_products(query=query, ean=ean)

            if not products:
                return [
                    TextContent(
                        type="text",
                        text=f"No products found for: {ean or query}",
                    )
                ]

            # Format products as readable text
            result_lines = [f"Found {len(products)} product(s):\n"]
            for i, product in enumerate(products, 1):
                result_lines.append(f"\n{i}. {product.name}")
                result_lines.append(f"   ID: {product.id}")
                if product.maker:
                    result_lines.append(f"   Maker: {product.maker}")
                if product.ean:
                    result_lines.append(f"   EAN: {product.ean}")
                result_lines.append(f"   Price: €{product.price}")
                if product.original_price:
                    result_lines.append(
                        f"   Original Price: €{product.original_price} (DISCOUNTED)"
                    )
                result_lines.append(f"   Available: {'Yes' if product.available else 'No'}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "sklavenitis_add_to_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]
            quantity = arguments.get("quantity", 1)

            success = sklavenitis_client.add_to_cart(product_id, quantity)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully added product {product_id} (quantity: {quantity}) to cart",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to add product {product_id} to cart",
                    )
                ]

        elif name == "sklavenitis_remove_from_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]

            success = sklavenitis_client.remove_from_cart(product_id)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully removed product {product_id} from cart",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to remove product {product_id} from cart",
                    )
                ]

        elif name == "sklavenitis_update_cart_quantity":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]
            quantity = arguments["quantity"]

            success = sklavenitis_client.update_cart_item_quantity(product_id, quantity)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully updated product {product_id} to quantity {quantity}",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to update product {product_id} quantity",
                    )
                ]

        elif name == "sklavenitis_get_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD in the MCP settings.",
                    )
                ]

            cart = sklavenitis_client.get_cart()

            if not cart.items:
                return [TextContent(type="text", text="Your cart is empty")]

            result_lines = [f"Shopping Cart ({cart.item_count} items):\n"]
            for i, item in enumerate(cart.items, 1):
                result_lines.append(f"\n{i}. {item.product.name}")
                result_lines.append(f"   Product ID: {item.product.id}")
                result_lines.append(f"   Price: €{item.product.price}")
                result_lines.append(f"   Quantity: {item.quantity}")
                result_lines.append(f"   Subtotal: €{item.subtotal}")

            result_lines.append(f"\n{'='*50}")
            result_lines.append(f"Total: €{cart.total}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "sklavenitis_get_orders":
            # Ensure we're authenticated before accessing orders
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD in the MCP settings.",
                    )
                ]

            include_history = arguments.get("include_history", True)
            orders = sklavenitis_client.get_orders(include_history=include_history)

            if not orders:
                return [
                    TextContent(
                        type="text",
                        text="No orders found" if include_history else "No current orders",
                    )
                ]

            result_lines = [f"Found {len(orders)} order(s):\n"]
            for i, order in enumerate(orders, 1):
                result_lines.append(f"\n{i}. Order #{order.order_number}")
                result_lines.append(f"   Status: {order.status}")
                result_lines.append(f"   Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
                result_lines.append(f"   Total: €{order.total}")
                if order.delivery_date:
                    result_lines.append(
                        f"   Delivery: {order.delivery_date.strftime('%Y-%m-%d %H:%M')}"
                    )

            return [TextContent(type="text", text="\n".join(result_lines))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Error: {str(e)}",
            )
        ]


async def main() -> None:
    """Main entry point for the MCP server."""
    global auth_manager, sklavenitis_client, credentials

    # Initialize authentication manager and client
    auth_manager = AuthManager()
    sklavenitis_client = SklavenitisClient(auth_manager, language="el")

    # Load credentials from environment variables
    email = os.environ.get("SKLAVENITIS_EMAIL")
    password = os.environ.get("SKLAVENITIS_PASSWORD")

    if email and password:
        credentials = AuthCredentials(email=email, password=password)
        logger.info(f"Credentials loaded from environment for: {email}")
    else:
        logger.warning("No credentials found in environment variables (SKLAVENITIS_EMAIL, SKLAVENITIS_PASSWORD)")
        logger.warning("Cart and order operations will require manual login via sklavenitis_login tool")

    logger.info("Starting Sklavenitis MCP Server...")

    # Import and run the server
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
