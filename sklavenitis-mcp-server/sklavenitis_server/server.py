"""MCP Server for Sklavenitis."""

import asyncio
import logging
import os
from typing import Any, Optional

from mcp.server import Server
from mcp.types import Resource, Tool, TextContent
from pydantic import AnyUrl

from .auth import AuthManager
from .sklavenitis_client import SklavenitisClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sklavenitis-mcp-server")

# Initialize server
app = Server("sklavenitis-mcp-server")

# Global state
auth_manager: AuthManager
client: SklavenitisClient
credentials: Optional[tuple[str, str]] = None  # (email, password)


async def ensure_authenticated() -> bool:
    """Ensure client is authenticated, auto-login if needed."""
    if auth_manager.is_authenticated:
        return True

    # Try to auto-login with stored credentials
    if credentials:
        email, password = credentials
        try:
            logger.info("Auto-logging in...")
            success = await client.login(email, password)
            if success:
                logger.info("Auto-login successful")
                return True
            else:
                logger.warning("Auto-login failed (likely due to reCAPTCHA)")
                logger.warning("Please login manually via your browser and extract cookies")
        except Exception as e:
            logger.error(f"Auto-login error: {e}")

    return False


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    resources = []

    if auth_manager.is_authenticated:
        resources.append(
            Resource(
                uri=AnyUrl("sklavenitis://cart"),
                name="Shopping Cart",
                mimeType="application/json",
                description="Current shopping cart contents",
            )
        )

    return resources


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read a resource by URI."""
    uri_str = str(uri)

    if uri_str == "sklavenitis://cart":
        if not auth_manager.is_authenticated:
            return "Error: Not authenticated. Please login first."

        cart = client.get_cart()
        return cart.model_dump_json(indent=2)

    raise ValueError(f"Unknown resource: {uri}")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="sklavenitis_login",
            description="Authenticate with Sklavenitis using email and password",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email address (optional if SKLAVENITIS_EMAIL configured)",
                    },
                    "password": {
                        "type": "string",
                        "description": "Password (optional if SKLAVENITIS_PASSWORD configured)",
                    },
                },
            },
        ),
        Tool(
            name="sklavenitis_logout",
            description="Logout and clear session",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sklavenitis_search_products",
            description="Search for products by name (supports Greek)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (e.g., 'γάλα', 'ψωμί', 'milk')",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="sklavenitis_add_to_cart",
            description="Add product to cart (auto-selects first available delivery slot, verifies addition)",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_sku": {
                        "type": "string",
                        "description": "Product SKU from search results",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add (default: 1)",
                        "default": 1,
                    },
                },
                "required": ["product_sku"],
            },
        ),
        Tool(
            name="sklavenitis_get_cart",
            description="Get current shopping cart contents",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sklavenitis_remove_from_cart",
            description="Remove product from cart",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_sku": {
                        "type": "string",
                        "description": "Product SKU to remove",
                    },
                },
                "required": ["product_sku"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "sklavenitis_login":
            email = arguments.get("email")
            password = arguments.get("password")

            # Use provided credentials or fall back to environment
            if not email or not password:
                if credentials:
                    email = credentials[0] if not email else email
                    password = credentials[1] if not password else password
                else:
                    return [
                        TextContent(
                            type="text",
                            text="Error: No credentials provided and SKLAVENITIS_EMAIL/SKLAVENITIS_PASSWORD not configured.",
                        )
                    ]

            success = await client.login(email, password)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"✅ Successfully logged in as {email}\nSession cookies saved for future use.",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text="❌ Login failed. This is likely due to reCAPTCHA enforcement.\n\n"
                             "**Workaround:**\n"
                             "1. Login manually at https://www.sklavenitis.gr\n"
                             "2. Extract cookies from your browser (F12 → Application → Cookies)\n"
                             "3. Save to ~/.sklavenitis_cookies.json\n"
                             "4. Try again - the server will use those cookies automatically",
                    )
                ]

        elif name == "sklavenitis_logout":
            client.logout()
            return [TextContent(type="text", text="✅ Successfully logged out")]

        elif name == "sklavenitis_search_products":
            query = arguments.get("query")
            if not query:
                return [TextContent(type="text", text="Error: Query parameter required")]

            products = client.search_products(query)

            if not products:
                return [TextContent(type="text", text=f"No products found for: {query}")]

            result_lines = [f"Found {len(products)} product(s):\n"]
            for i, product in enumerate(products, 1):
                result_lines.append(f"\n{i}. {product.name}")
                result_lines.append(f"   SKU: {product.id}")
                if product.description:
                    result_lines.append(f"   Category: {product.description}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "sklavenitis_add_to_cart":
            # Ensure authenticated
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD, "
                             "or use sklavenitis_login first.",
                    )
                ]

            product_sku = arguments["product_sku"]
            quantity = arguments.get("quantity", 1)

            success = client.add_to_cart(product_sku, quantity)

            if success:
                # Get updated cart to show delivery info
                cart = client.get_cart()
                delivery_info = cart.slot_info if cart.slot_info else "Not set"

                return [
                    TextContent(
                        type="text",
                        text=f"✅ Successfully added product {product_sku} (quantity: {quantity}) to cart\n"
                             f"Delivery slot: {delivery_info}",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Failed to add product {product_sku} to cart (may be out of stock or unavailable)",
                    )
                ]

        elif name == "sklavenitis_get_cart":
            # Ensure authenticated
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD, "
                             "or use sklavenitis_login first.",
                    )
                ]

            cart = client.get_cart()

            if int(cart.summary_text) == 0:
                return [TextContent(type="text", text="Your cart is empty")]

            result_lines = [f"Shopping Cart ({cart.summary_text} items):\n"]
            result_lines.append(f"Total: {cart.grand_total}")
            if cart.slot_info:
                result_lines.append(f"Delivery: {cart.slot_info}")

            if cart.items:
                result_lines.append("\nItems:")
                for sku, item in cart.items.items():
                    result_lines.append(f"  - SKU {sku}: Quantity {item.quantity}")

            return [TextContent(type="text", text="\n".join(result_lines))]

        elif name == "sklavenitis_remove_from_cart":
            # Ensure authenticated
            if not await ensure_authenticated():
                return [
                    TextContent(
                        type="text",
                        text="Error: Not authenticated. Please configure SKLAVENITIS_EMAIL and SKLAVENITIS_PASSWORD, "
                             "or use sklavenitis_login first.",
                    )
                ]

            product_sku = arguments["product_sku"]
            success = client.remove_from_cart(product_sku)

            if success:
                return [
                    TextContent(
                        type="text",
                        text=f"✅ Successfully removed product {product_sku} from cart",
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Failed to remove product {product_sku} from cart (may not be in cart)",
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
    """Main entry point."""
    global auth_manager, client, credentials

    # Load configuration from environment
    email = os.environ.get("SKLAVENITIS_EMAIL")
    password = os.environ.get("SKLAVENITIS_PASSWORD")
    zipcode = os.environ.get("SKLAVENITIS_ZIPCODE")

    # Initialize auth manager and client
    auth_manager = AuthManager(zipcode=zipcode)
    client = SklavenitisClient(auth_manager)

    if email and password:
        credentials = (email, password)
        logger.info(f"Credentials loaded from environment for: {email}")
    else:
        logger.warning(
            "No credentials found in environment variables (SKLAVENITIS_EMAIL, SKLAVENITIS_PASSWORD)"
        )
        logger.warning("You can login manually via sklavenitis_login tool")

    if zipcode:
        logger.info(f"Zipcode/HubID configured: {zipcode}")
    else:
        logger.info("No zipcode configured (SKLAVENITIS_ZIPCODE). Using default or saved Zone cookie.")

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

