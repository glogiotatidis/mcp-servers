"""HTTP server for Skroutz MCP Server with hot reloading support and SSE."""

import logging
import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import AuthManager
from .skroutz_client_cffi import SkroutzClientCffi
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("skroutz-http-server")

# Global state
auth_manager: AuthManager
skroutz_client: SkroutzClientCffi
credentials: Optional[AuthCredentials] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global auth_manager, skroutz_client, credentials

    # Startup
    logger.info("Starting Skroutz HTTP Server...")
    auth_manager = AuthManager()
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

    yield

    # Shutdown
    logger.info("Shutting down Skroutz HTTP Server...")
    skroutz_client.close()


app = FastAPI(
    title="Skroutz MCP Server",
    description="HTTP API for interacting with skroutz.gr e-commerce store",
    version="0.1.0",
    lifespan=lifespan,
)


# Request/Response Models
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str


class SearchRequest(BaseModel):
    query: str


class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = 1


class RemoveFromCartRequest(BaseModel):
    product_id: str


class UpdateCartRequest(BaseModel):
    product_id: str
    quantity: int


class OrdersRequest(BaseModel):
    include_history: bool = True


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Skroutz MCP Server",
        "version": "0.1.0",
        "description": "HTTP API for interacting with skroutz.gr e-commerce store",
        "mcp_compatible": True,
        "home_assistant_compatible": True,
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "sse": "/sse - SSE endpoint for Home Assistant MCP integration",
            "auth": {
                "login": "POST /auth/login",
                "logout": "POST /auth/logout",
                "status": "GET /auth/status"
            },
            "products": {
                "search": "POST /products/search"
            },
            "cart": {
                "get": "GET /cart",
                "add": "POST /cart/add",
                "remove": "POST /cart/remove",
                "update": "POST /cart/update"
            },
            "orders": {
                "list": "POST /orders",
                "details": "GET /orders/{order_id}"
            }
        },
        "home_assistant_setup": {
            "recommended": "Use mcp-proxy for full MCP protocol support",
            "mcp_proxy_install": "npm install -g @chrishayuk/mcp-proxy",
            "mcp_proxy_command": "mcp-proxy --stdio 'python -m skroutz_server' --port 8080",
            "sse_url": "http://localhost:8080/sse"
        },
        "authenticated": auth_manager.is_authenticated() if auth_manager else False
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "authenticated": auth_manager.is_authenticated() if auth_manager else False,
    }


# Authentication endpoints
@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login to skroutz.gr."""
    try:
        login_credentials = AuthCredentials(email=request.email, password=request.password)
        success = skroutz_client.login(login_credentials)

        if success:
            return LoginResponse(
                success=True, message=f"Successfully logged in as {request.email}"
            )
        else:
            return LoginResponse(success=False, message="Login failed. Check your credentials.")
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/logout")
async def logout():
    """Logout from skroutz.gr."""
    try:
        skroutz_client.logout()
        return {"success": True, "message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/status")
async def auth_status():
    """Get authentication status."""
    return {
        "authenticated": auth_manager.is_authenticated(),
        "email": auth_manager.session.user_email if auth_manager.is_authenticated() else None,
    }


# Product endpoints
@app.post("/products/search")
async def search_products(request: SearchRequest):
    """Search for products by name."""
    try:
        products = skroutz_client.search_products(query=request.query)

        return {
            "count": len(products),
            "products": [product.model_dump() for product in products],
        }
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Cart endpoints
@app.get("/cart")
async def get_cart():
    """Get current shopping cart."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        cart = skroutz_client.get_cart()
        return cart.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get cart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cart/add")
async def add_to_cart(request: AddToCartRequest):
    """Add a product to the cart."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        product_url_or_id = request.product_id

        # Get product details and add to cart
        logger.info(f"Adding to cart: {product_url_or_id}")
        details = skroutz_client.get_product_details_for_cart(product_url_or_id)

        if not details or not details.get('product_id'):
            return {
                "success": False,
                "message": "Could not extract product details. Product may not support 'Αγορά μέσω Skroutz'.",
            }

        success = skroutz_client.add_to_cart(
            sku_id=details.get('sku_id', product_url_or_id),
            product_id=details['product_id'],
            shop_id=details['shop_id'],
            price=details['price'],
            quantity=request.quantity
        )

        if success:
            return {
                "success": True,
                "message": f"Added product to cart (quantity: {request.quantity})",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to add product to cart. Product may not support 'Αγορά μέσω Skroutz'.",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add to cart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cart/remove")
async def remove_from_cart(request: RemoveFromCartRequest):
    """Remove a product from the cart."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        success = skroutz_client.remove_from_cart(request.product_id)

        if success:
            return {"success": True, "message": f"Removed product {request.product_id} from cart"}
        else:
            return {"success": False, "message": f"Failed to remove product {request.product_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove from cart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cart/update")
async def update_cart(request: UpdateCartRequest):
    """Update product quantity in cart."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        success = skroutz_client.update_cart_item_quantity(request.product_id, request.quantity)

        if success:
            return {
                "success": True,
                "message": f"Updated product {request.product_id} to quantity {request.quantity}",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to update product {request.product_id} quantity",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update cart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Order endpoints
@app.post("/orders")
async def get_orders(request: OrdersRequest):
    """Get user's orders."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        orders = skroutz_client.get_orders(include_history=request.include_history)

        return {
            "count": len(orders),
            "orders": [order.model_dump() for order in orders],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get orders error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders/{order_id}")
async def get_order_details(order_id: str):
    """Get detailed information for a specific order."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        order = skroutz_client.get_order_details(order_id)

        if not order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

        return order.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order details error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# SSE endpoint for Home Assistant MCP integration
# Note: This is a simplified SSE endpoint. For full MCP SSE support,
# use the mcp-proxy tool to wrap the stdio server.
@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    Server-Sent Events (SSE) endpoint for MCP protocol compatibility.

    This endpoint provides a simple SSE stream that Home Assistant can connect to.
    For full MCP protocol support with Home Assistant, it's recommended to use
    an MCP proxy like mcp-proxy (https://github.com/chrishayuk/mcp-proxy) which
    properly bridges stdio MCP servers to SSE.

    To use with Home Assistant:
    1. Install mcp-proxy: npm install -g @chrishayuk/mcp-proxy
    2. Run: mcp-proxy --stdio "python -m skroutz_server" --port 8080
    3. Configure Home Assistant with: http://localhost:8080/sse

    Reference: https://www.home-assistant.io/integrations/mcp/
    """

    async def event_stream():
        """Generate SSE keepalive stream."""
        try:
            logger.info("SSE client connected for MCP")

            # Send endpoint info event
            info = {
                "type": "info",
                "server": "skroutz-mcp-server",
                "version": "0.1.0",
                "transport": "sse",
                "note": "For full MCP protocol support, use mcp-proxy to wrap the stdio server",
                "stdio_command": "python -m skroutz_server",
                "mcp_proxy_usage": "mcp-proxy --stdio 'python -m skroutz_server' --port 8080"
            }
            yield f"data: {json.dumps(info)}\n\n"

            # Keep connection alive
            while True:
                if await request.is_disconnected():
                    logger.info("SSE client disconnected")
                    break

                # Send keepalive ping every 30 seconds
                yield ": ping\n\n"
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("SSE stream cancelled")
        except Exception as e:
            logger.error(f"SSE error: {e}", exc_info=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


def run_http_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """
    Run the HTTP server.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        reload: Enable hot reloading (default: False)
    """
    import uvicorn

    logger.info(f"Starting server on {host}:{port} (reload={'enabled' if reload else 'disabled'})")

    if reload:
        # Hot reloading - watches for file changes
        uvicorn.run(
            "skroutz_server.http_server:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=["skroutz_server"],
            log_level="info"
        )
    else:
        # Regular mode
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    # Enable hot reloading by default when running directly
    run_http_server(reload=True)

