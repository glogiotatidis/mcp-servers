"""MCP Server for E-Fresh.gr grocery store."""

import asyncio
import logging
import os
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import AnyUrl

from .auth import AuthManager
from .efresh_client import EFreshClient
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("efresh-mcp-server")

# Initialize server
app = Server("efresh-mcp-server")

# Global state
auth_manager: AuthManager
efresh_client: EFreshClient
credentials: Optional[AuthCredentials] = None


async def ensure_authenticated() -> bool:
    """Ensure the client is authenticated, auto-login if credentials are available."""
    if auth_manager.is_authenticated():
        return True

    # Try to auto-login with stored credentials
    if credentials:
        try:
            logger.info("Auto-logging in with configured credentials...")
            success = await efresh_client.login(credentials)
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
                    uri=AnyUrl("efresh://cart"),
                    name="Shopping Cart",
                    mimeType="application/json",
                    description="Current shopping cart contents",
                ),
                Resource(
                    uri=AnyUrl("efresh://orders"),
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

    if uri_str == "efresh://cart":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        cart = efresh_client.get_cart()
        return cart.model_dump_json(indent=2)

    elif uri_str == "efresh://orders":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        orders = efresh_client.get_orders()
        result = [order.model_dump() for order in orders]
        import json

        return json.dumps(result, indent=2, default=str)

    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="efresh_login",
            description="Authenticate with e-fresh.gr. Uses credentials from environment (EFRESH_EMAIL, EFRESH_PASSWORD) if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "User email address (optional if EFRESH_EMAIL is configured)",
                    },
                    "password": {
                        "type": "string",
                        "description": "User password (optional if EFRESH_PASSWORD is configured)",
                    },
                },
            },
        ),
        Tool(
            name="efresh_logout",
            description="Logout from e-fresh.gr and clear session",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="efresh_search_products",
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
            name="efresh_add_to_cart",
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
            name="efresh_remove_from_cart",
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
            name="efresh_update_cart_quantity",
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
            name="efresh_get_cart",
            description="Get current shopping cart contents with all items and total",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="efresh_get_orders",
            description="Get user's orders (current and/or past orders). Can optionally include full item details for each order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_history": {
                        "type": "boolean",
                        "description": "Include past orders (default: true)",
                        "default": True,
                    },
                    "include_items": {
                        "type": "boolean",
                        "description": "Fetch full order details including items for each order (default: false)",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="efresh_get_order_details",
            description="Get detailed information for a specific order, including all items",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID to fetch details for",
                    },
                },
                "required": ["order_id"],
            },
        ),
        Tool(
            name="efresh_set_language",
            description="Set the interface language for e-fresh.gr (Greek or English)",
            inputSchema={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["el", "en"],
                        "description": "Language code: 'el' for Greek, 'en' for English",
                    },
                },
                "required": ["language"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "efresh_login":
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
                            text="Error: No credentials provided and EFRESH_EMAIL/EFRESH_PASSWORD not configured.",
                        )
                    ]

            login_credentials = AuthCredentials(email=email, password=password)
            success = await efresh_client.login(login_credentials)

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

        elif name == "efresh_logout":
            efresh_client.logout()
            return [TextContent(type="text", text="Successfully logged out")]

        elif name == "efresh_search_products":
            query = arguments.get("query")
            ean = arguments.get("ean")

            products = efresh_client.search_products(query=query, ean=ean)

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
                if product.unit:
                    result_lines.append(f"   Unit: {product.unit}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "efresh_add_to_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]
            quantity = arguments.get("quantity", 1)

            success = efresh_client.add_to_cart(product_id, quantity)

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

        elif name == "efresh_remove_from_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]

            success = efresh_client.remove_from_cart(product_id)

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

        elif name == "efresh_update_cart_quantity":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]
            quantity = arguments["quantity"]

            success = efresh_client.update_cart_item_quantity(product_id, quantity)

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

        elif name == "efresh_get_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            cart = efresh_client.get_cart()

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

        elif name == "efresh_get_orders":
            # Ensure we're authenticated before accessing orders
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            include_history = arguments.get("include_history", True)
            include_items = arguments.get("include_items", False)
            orders = efresh_client.get_orders(include_history=include_history, include_items=include_items)

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
                if order.items:
                    result_lines.append(f"   Items ({len(order.items)}):")
                    for item in order.items:
                        result_lines.append(
                            f"     - {item.product_name} x{item.quantity} (€{item.subtotal})"
                        )

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "efresh_get_order_details":
            # Ensure we're authenticated before accessing orders
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure EFRESH_EMAIL and EFRESH_PASSWORD in the MCP settings.",
                    )
                ]

            order_id = arguments["order_id"]
            order = efresh_client.get_order_details(order_id)

            if not order:
                return [
                    TextContent(
                        type="text",
                        text=f"Order {order_id} not found",
                    )
                ]

            result_lines = [f"Order Details:\n"]
            result_lines.append(f"Order #{order.order_number}")
            result_lines.append(f"Status: {order.status}")
            result_lines.append(f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
            result_lines.append(f"Total: €{order.total}")
            if order.delivery_date:
                result_lines.append(
                    f"Delivery: {order.delivery_date.strftime('%Y-%m-%d %H:%M')}"
                )
            if order.delivery_address:
                result_lines.append(f"Delivery Address: {order.delivery_address}")

            if order.items:
                result_lines.append(f"\nItems ({len(order.items)}):")
                for i, item in enumerate(order.items, 1):
                    result_lines.append(f"\n{i}. {item.product_name}")
                    result_lines.append(f"   Quantity: {item.quantity}")
                    result_lines.append(f"   Price: €{item.price}")
                    result_lines.append(f"   Subtotal: €{item.subtotal}")
            else:
                result_lines.append("\nNo items found for this order")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "efresh_set_language":
            language = arguments["language"]
            efresh_client.set_language(language)

            lang_name = "Greek" if language == "el" else "English"
            return [
                TextContent(
                    type="text",
                    text=f"Language set to {lang_name} ({language})",
                )
            ]

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
    global auth_manager, efresh_client, credentials

    # Initialize authentication manager and client
    auth_manager = AuthManager()
    efresh_client = EFreshClient(auth_manager, language="el")

    # Load credentials from environment variables
    email = os.environ.get("EFRESH_EMAIL")
    password = os.environ.get("EFRESH_PASSWORD")

    if email and password:
        credentials = AuthCredentials(email=email, password=password)
        logger.info(f"Credentials loaded from environment for: {email}")
    else:
        logger.warning("No credentials found in environment variables (EFRESH_EMAIL, EFRESH_PASSWORD)")
        logger.warning("Cart and order operations will require manual login via efresh_login tool")

    logger.info("Starting E-Fresh MCP Server...")

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
