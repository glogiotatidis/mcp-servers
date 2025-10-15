"""Hybrid Skroutz client using curl_cffi for search and Playwright for cart operations."""

import logging
from typing import Optional

from .auth import AuthManager
from .skroutz_client_cffi import SkroutzClientCffi
from .skroutz_client_playwright import SkroutzClientPlaywright
from .models import AuthCredentials, Cart, Order, Product

logger = logging.getLogger(__name__)


class SkroutzClientHybrid:
    """
    Hybrid client that uses:
    - curl_cffi for fast search operations (good Cloudflare bypass)
    - Playwright for cart operations (better for interactive features)
    """

    def __init__(self, auth_manager: AuthManager, headless: bool = True) -> None:
        """
        Initialize the hybrid client.

        Args:
            auth_manager: Authentication manager instance
            headless: Run Playwright browser in headless mode
        """
        self.auth_manager = auth_manager
        self.headless = headless

        # Initialize both clients
        self.cffi_client = SkroutzClientCffi(auth_manager)
        self.playwright_client: Optional[SkroutzClientPlaywright] = None

        logger.info("Hybrid client initialized (curl_cffi for search, Playwright for cart)")

    async def _ensure_playwright(self) -> SkroutzClientPlaywright:
        """Lazily initialize Playwright client when needed."""
        if self.playwright_client is None:
            self.playwright_client = SkroutzClientPlaywright(
                self.auth_manager,
                headless=self.headless
            )
            logger.info("Playwright client initialized for cart operations")
        return self.playwright_client

    def login(self, credentials: AuthCredentials) -> bool:
        """
        Authenticate with skroutz.gr using curl_cffi.

        Args:
            credentials: User credentials

        Returns:
            True if login successful
        """
        return self.cffi_client.login(credentials)

    def logout(self) -> None:
        """Logout and clear session."""
        self.cffi_client.logout()
        if self.playwright_client:
            # Note: logout in playwright client is async, but we'll just clear session
            self.playwright_client.auth_manager.clear_session()

    async def search_products(self, query: str) -> list[Product]:
        """
        Search for products using Playwright for reliable Cloudflare bypass.

        Args:
            query: Search query

        Returns:
            List of products with price, availability, and URLs
        """
        logger.info(f"Using Playwright for search: {query}")
        playwright_client = await self._ensure_playwright()
        products = await playwright_client.search_products(query)
        logger.info(f"Found {len(products)} products")
        return products

    async def add_to_cart(self, product_url: str, quantity: int = 1) -> bool:
        """
        Add product to cart using Playwright (better for interactive features).

        Args:
            product_url: Full product URL from search results
            quantity: Quantity to add

        Returns:
            True if successful
        """
        logger.info(f"Using Playwright for add_to_cart: {product_url}")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.add_to_cart(product_url, quantity)

    async def remove_from_cart(self, product_id: str) -> bool:
        """
        Remove product from cart using Playwright.

        Args:
            product_id: Product ID to remove

        Returns:
            True if successful
        """
        logger.info(f"Using Playwright for remove_from_cart: {product_id}")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.remove_from_cart(product_id)

    async def update_cart_item_quantity(self, product_id: str, quantity: int) -> bool:
        """
        Update cart item quantity using Playwright.

        Args:
            product_id: Product ID to update
            quantity: New quantity

        Returns:
            True if successful
        """
        logger.info(f"Using Playwright for update_cart_quantity: {product_id} -> {quantity}")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.update_cart_item_quantity(product_id, quantity)

    async def get_cart(self) -> Cart:
        """
        Get cart contents using Playwright.

        Returns:
            Cart object
        """
        logger.info("Using Playwright for get_cart")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.get_cart()

    async def get_orders(self, include_history: bool = True) -> list[Order]:
        """
        Get orders using Playwright.

        Args:
            include_history: Include order history

        Returns:
            List of orders
        """
        logger.info("Using Playwright for get_orders")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.get_orders(include_history)

    async def get_order_details(self, order_id: str) -> Optional[Order]:
        """
        Get order details using Playwright.

        Args:
            order_id: Order ID

        Returns:
            Order object or None
        """
        logger.info(f"Using Playwright for get_order_details: {order_id}")
        playwright_client = await self._ensure_playwright()
        return await playwright_client.get_order_details(order_id)

    async def close(self) -> None:
        """Clean up resources."""
        self.cffi_client.close()
        if self.playwright_client:
            await self.playwright_client.close()

