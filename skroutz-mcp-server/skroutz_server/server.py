"""MCP Server for Skroutz.gr e-commerce store."""

import asyncio
import logging
import os
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Resource, Tool, TextContent
from pydantic import AnyUrl

from .auth import AuthManager
from .skroutz_client_cffi import SkroutzClientCffi
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skroutz-mcp-server")

# Initialize server
app = Server("skroutz-mcp-server")

# Global state
auth_manager: AuthManager
skroutz_client: SkroutzClientCffi
credentials: Optional[AuthCredentials] = None


async def ensure_authenticated() -> bool:
    """Ensure the client is authenticated, auto-login if credentials are available."""
    if auth_manager.is_authenticated():
        return True

    # Try to auto-login with stored credentials
    if credentials:
        try:
            logger.info("Auto-logging in with configured credentials...")
            success = skroutz_client.login(credentials)
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
                    uri=AnyUrl("skroutz://cart"),
                    name="Shopping Cart",
                    mimeType="application/json",
                    description="Current shopping cart contents",
                ),
                Resource(
                    uri=AnyUrl("skroutz://orders"),
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

    if uri_str == "skroutz://cart":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        cart = skroutz_client.get_cart()
        return cart.model_dump_json(indent=2)

    elif uri_str == "skroutz://orders":
        if not auth_manager.is_authenticated():
            return "Error: Not authenticated. Please login first."

        orders = skroutz_client.get_orders()
        result = [order.model_dump() for order in orders]
        import json

        return json.dumps(result, indent=2, default=str)

    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="skroutz_login",
            description="Authenticate with skroutz.gr. Uses credentials from environment (SKROUTZ_EMAIL, SKROUTZ_PASSWORD) if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "User email address (optional if SKROUTZ_EMAIL is configured)",
                    },
                    "password": {
                        "type": "string",
                        "description": "User password (optional if SKROUTZ_PASSWORD is configured)",
                    },
                },
            },
        ),
        Tool(
            name="skroutz_logout",
            description="Logout from skroutz.gr and clear session",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="skroutz_search_products",
            description="Search for products by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product name or search term",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="skroutz_add_to_cart",
            description="Add a product to the shopping cart",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product URL (from search results) or Product ID to add to cart",
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
            name="skroutz_remove_from_cart",
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
            name="skroutz_update_cart_quantity",
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
            name="skroutz_get_cart",
            description="Get current shopping cart contents with all items and total",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="skroutz_get_orders",
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
        Tool(
            name="skroutz_get_order_details",
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
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "skroutz_login":
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
                            text="Error: No credentials provided and SKROUTZ_EMAIL/SKROUTZ_PASSWORD not configured.",
                        )
                    ]

            login_credentials = AuthCredentials(email=email, password=password)
            success = skroutz_client.login(login_credentials)

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

        elif name == "skroutz_logout":
            skroutz_client.logout()
            return [TextContent(type="text", text="Successfully logged out")]

        elif name == "skroutz_search_products":
            query = arguments["query"]
            products = skroutz_client.search_products(query=query)

            if not products:
                return [
                    TextContent(
                        type="text",
                        text=f"No products found for: {query}",
                    )
                ]

            # Format products as readable text
            result_lines = [f"Found {len(products)} product(s):\n"]
            for i, product in enumerate(products, 1):
                result_lines.append(f"\n{i}. {product.name}")
                result_lines.append(f"   ID: {product.id}")
                if product.maker:
                    result_lines.append(f"   Maker: {product.maker}")
                result_lines.append(f"   Price: €{product.price}")
                if product.original_price:
                    result_lines.append(
                        f"   Original Price: €{product.original_price} (DISCOUNTED)"
                    )
                result_lines.append(f"   Available: {'Yes' if product.available else 'No'}")
                if product.url:
                    result_lines.append(f"   URL: {product.url}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "skroutz_add_to_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            product_url_or_id = arguments["product_id"]
            quantity = arguments.get("quantity", 1)

            # Extract details and add to cart
            logger.info(f"Adding to cart: {product_url_or_id}")
            details = skroutz_client.get_product_details_for_cart(product_url_or_id)

            if not details or not details.get('product_id'):
                return [
                    TextContent(
                        type="text",
                        text=f"Could not extract product details. Product may not support 'Αγορά μέσω Skroutz'.",
                    )
                ]

            success = skroutz_client.add_to_cart(
                sku_id=details.get('sku_id', product_url_or_id),
                product_id=details['product_id'],
                shop_id=details['shop_id'],
                price=details['price'],
                quantity=quantity
            )

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"Successfully added product {product_url_or_id} (quantity: {quantity}) to cart",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"Failed to add product {product_url_or_id} to cart",
                    )
                ]

        elif name == "skroutz_remove_from_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]

            success = skroutz_client.remove_from_cart(product_id)

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

        elif name == "skroutz_update_cart_quantity":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            product_id = arguments["product_id"]
            quantity = arguments["quantity"]

            success = skroutz_client.update_cart_item_quantity(product_id, quantity)

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

        elif name == "skroutz_get_cart":
            # Ensure we're authenticated before cart operations
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            try:
                cart = skroutz_client.get_cart()
            except Exception as e:
                error_msg = str(e)
                if "cloudflare" in error_msg.lower():
                    return [
                        TextContent(
                            type="text",
                            text=f"⚠️  Cloudflare Protection Detected\n\nThe cart request was blocked by Cloudflare's anti-bot protection.\n\nThis is a temporary limitation - curl_cffi may need additional browser fingerprinting or the site may be under heavy protection.\n\nDetails: {error_msg}",
                        )
                    ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error fetching cart: {error_msg}",
                        )
                    ]

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

        elif name == "skroutz_get_orders":
            # Ensure we're authenticated before accessing orders
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            include_history = arguments.get("include_history", True)

            try:
                orders = skroutz_client.get_orders(include_history=include_history)
            except Exception as e:
                error_msg = str(e)
                if "cloudflare" in error_msg.lower():
                    return [
                        TextContent(
                            type="text",
                            text=f"⚠️  Cloudflare Protection Detected\n\nThe orders request was blocked by Cloudflare's anti-bot protection.\n\nDetails: {error_msg}",
                        )
                    ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error fetching orders: {error_msg}",
                        )
                    ]

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

        elif name == "skroutz_get_order_details":
            # Ensure we're authenticated before accessing orders
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKROUTZ_EMAIL and SKROUTZ_PASSWORD in the MCP settings.",
                    )
                ]

            order_id = arguments["order_id"]
            order = skroutz_client.get_order_details(order_id)

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
    global auth_manager, skroutz_client, credentials

    # Initialize authentication manager and client
    auth_manager = AuthManager()
    # Use curl_cffi for all operations
    skroutz_client = SkroutzClientCffi(auth_manager)
    logger.info("Using curl_cffi client for all operations")

    # Load credentials from environment variables
    email = os.environ.get("SKROUTZ_EMAIL")
    password = os.environ.get("SKROUTZ_PASSWORD")

    if email and password:
        credentials = AuthCredentials(email=email, password=password)
        logger.info(f"Credentials loaded from environment for: {email}")
    else:
        logger.warning("No credentials found in environment variables (SKROUTZ_EMAIL, SKROUTZ_PASSWORD)")
        logger.warning("Cart and order operations will require manual login via skroutz_login tool")

    logger.info("Starting Skroutz MCP Server...")

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
