"""HTTP server for E-Fresh MCP Server."""

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .auth import AuthManager
from .efresh_client import EFreshClient
from .models import AuthCredentials

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("efresh-http-server")

# Global state
auth_manager: AuthManager
efresh_client: EFreshClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global auth_manager, efresh_client

    # Startup
    logger.info("Starting E-Fresh HTTP Server...")
    auth_manager = AuthManager()
    efresh_client = EFreshClient(auth_manager, language="el")

    yield

    # Shutdown
    logger.info("Shutting down E-Fresh HTTP Server...")
    efresh_client.close()


app = FastAPI(
    title="E-Fresh MCP Server",
    description="HTTP API for interacting with e-fresh.gr grocery store",
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
    query: Optional[str] = None
    ean: Optional[str] = None


class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = 1


class RemoveFromCartRequest(BaseModel):
    product_id: str


class LanguageRequest(BaseModel):
    language: str


class OrdersRequest(BaseModel):
    include_history: bool = True


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "E-Fresh MCP Server",
        "version": "0.1.0",
        "description": "HTTP API for interacting with e-fresh.gr grocery store",
        "mcp_stdio": "python -m efresh_server",
        "home_assistant_setup": {
            "note": "Use mcp-proxy to wrap the stdio MCP server for Home Assistant",
            "install": "npm install -g @chrishayuk/mcp-proxy",
            "command": "mcp-proxy --stdio 'python -m efresh_server' --port 8081",
            "sse_endpoint": "http://localhost:8081/sse",
            "reference": "https://www.home-assistant.io/integrations/mcp/"
        },
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "auth": {"login": "POST /auth/login", "logout": "POST /auth/logout", "status": "GET /auth/status"},
            "products": {"search": "POST /products/search"},
            "cart": {"get": "GET /cart", "add": "POST /cart/add", "remove": "POST /cart/remove"},
            "orders": {"list": "POST /orders"},
            "settings": {"language": "POST /settings/language", "get_language": "GET /settings/language"}
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
    """Login to e-fresh.gr."""
    try:
        credentials = AuthCredentials(email=request.email, password=request.password)
        success = await efresh_client.login(credentials)

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
    """Logout from e-fresh.gr."""
    try:
        efresh_client.logout()
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
    """Search for products by name or EAN."""
    try:
        if not request.query and not request.ean:
            raise HTTPException(status_code=400, detail="Either query or ean must be provided")

        products = efresh_client.search_products(query=request.query, ean=request.ean)

        return {
            "count": len(products),
            "products": [product.model_dump() for product in products],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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

        cart = efresh_client.get_cart()
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

        success = efresh_client.add_to_cart(request.product_id, request.quantity)

        if success:
            return {
                "success": True,
                "message": f"Added product {request.product_id} (quantity: {request.quantity}) to cart",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to add product {request.product_id} to cart",
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

        success = efresh_client.remove_from_cart(request.product_id)

        if success:
            return {"success": True, "message": f"Removed product {request.product_id} from cart"}
        else:
            return {"success": False, "message": f"Failed to remove product {request.product_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove from cart error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Order endpoints
@app.post("/orders")
async def get_orders(request: OrdersRequest):
    """Get user's orders."""
    try:
        if not auth_manager.is_authenticated():
            raise HTTPException(status_code=401, detail="Not authenticated")

        orders = efresh_client.get_orders(include_history=request.include_history)

        return {
            "count": len(orders),
            "orders": [order.model_dump() for order in orders],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get orders error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Settings endpoints
@app.post("/settings/language")
async def set_language(request: LanguageRequest):
    """Set the interface language."""
    try:
        if request.language not in ["el", "en"]:
            raise HTTPException(status_code=400, detail="Language must be 'el' or 'en'")

        efresh_client.set_language(request.language)

        lang_name = "Greek" if request.language == "el" else "English"
        return {"success": True, "message": f"Language set to {lang_name} ({request.language})"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set language error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/settings/language")
async def get_language():
    """Get current language setting."""
    return {"language": efresh_client.language}


# MCP Tools endpoint (for compatibility with MCP clients over HTTP)
@app.get("/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools."""
    return {
        "tools": [
            {
                "name": "efresh_login",
                "description": "Authenticate with e-fresh.gr using email and password",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "User email address"},
                        "password": {"type": "string", "description": "User password"},
                    },
                    "required": ["email", "password"],
                },
            },
            {
                "name": "efresh_logout",
                "description": "Logout from e-fresh.gr and clear session",
            },
            {
                "name": "efresh_search_products",
                "description": "Search for products by name or EAN/barcode",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Product name or search term"},
                        "ean": {"type": "string", "description": "EAN/barcode for exact match"},
                    },
                },
            },
            {
                "name": "efresh_add_to_cart",
                "description": "Add a product to the shopping cart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "Product ID to add"},
                        "quantity": {
                            "type": "integer",
                            "description": "Quantity to add",
                            "default": 1,
                        },
                    },
                    "required": ["product_id"],
                },
            },
            {
                "name": "efresh_remove_from_cart",
                "description": "Remove a product from the shopping cart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "Product ID to remove"},
                    },
                    "required": ["product_id"],
                },
            },
            {
                "name": "efresh_get_cart",
                "description": "Get current shopping cart contents",
            },
            {
                "name": "efresh_get_orders",
                "description": "Get user's orders",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "include_history": {
                            "type": "boolean",
                            "description": "Include past orders",
                            "default": True,
                        },
                    },
                },
            },
            {
                "name": "efresh_set_language",
                "description": "Set the interface language",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "enum": ["el", "en"],
                            "description": "Language code",
                        },
                    },
                    "required": ["language"],
                },
            },
        ]
    }


def run_http_server(host: str = "0.0.0.0", port: int = 8001, reload: bool = False):
    """Run the HTTP server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_http_server()
