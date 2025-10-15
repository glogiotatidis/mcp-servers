"""HTTP server for Skroutz MCP Server with hot reloading support."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
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

