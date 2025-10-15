"""E-Fresh.gr API client."""

import logging
import re
from decimal import Decimal
from typing import Any, Optional
from datetime import datetime

import httpx
from .auth import AuthManager
from .models import AuthCredentials, Cart, CartItem, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class EFreshClient:
    """Client for interacting with e-fresh.gr API."""

    BASE_URL = "https://www.e-fresh.gr"

    def __init__(self, auth_manager: AuthManager, language: str = "el") -> None:
        """
        Initialize the e-fresh client.

        Args:
            auth_manager: Authentication manager instance
            language: Language code (el for Greek, en for English)
        """
        self.auth_manager = auth_manager
        self.language = language
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": f"{language},en-US;q=0.9,en;q=0.8",
            },
        )

    def _update_cookies(self) -> None:
        """Update client cookies from auth manager."""
        cookies = self.auth_manager.get_cookies()
        self.client.cookies.clear()
        for name, value in cookies.items():
            self.client.cookies.set(name, value)

    def _save_cookies(self) -> None:
        """Save current cookies to auth manager."""
        # Handle duplicate cookies by keeping only the last value
        cookies = {}
        for cookie in self.client.cookies.jar:
            cookies[cookie.name] = cookie.value
        if cookies:
            self.auth_manager.save_session(
                cookies=cookies, user_email=self.auth_manager.session.user_email
            )

    def set_language(self, language: str) -> None:
        """
        Set the interface language.

        Args:
            language: Language code (el for Greek, en for English)
        """
        self.language = language
        self.client.headers["Accept-Language"] = f"{language},en-US;q=0.9,en;q=0.8"

    async def login(self, credentials: AuthCredentials) -> bool:
        """
        Authenticate with e-fresh.gr.

        Args:
            credentials: User credentials (email and password)

        Returns:
            True if login successful, False otherwise

        Raises:
            Exception: If login fails with specific error message
        """
        logger.info(f"=== LOGIN: email={credentials.email} ===")

        # First, get the login page to retrieve CSRF token and session cookies
        login_page_url = f"/{self.language}/account/login"
        logger.info(f"Getting login page: {login_page_url}")
        response = self.client.get(login_page_url)
        response.raise_for_status()
        logger.info(f"Login page response: status={response.status_code}")

        # Extract CSRF token from page
        csrf_token = self._extract_csrf_token(response.text)
        logger.info(f"CSRF token: {'Found' if csrf_token else 'Not found'}")

        # Extract XSRF-TOKEN cookie for header (URL-decode it)
        xsrf_token = None
        for cookie in self.client.cookies.jar:
            if cookie.name == "XSRF-TOKEN":
                import urllib.parse
                xsrf_token = urllib.parse.unquote(cookie.value)
                break

        logger.info(f"XSRF token: {'Found' if xsrf_token else 'Not found'}")

        # Try API login (Vue.js SPA)
        logger.info("Attempting API login via /api/account/login...")
        login_response = self.client.post(
            "/api/account/login",
            json={
                "email": credentials.email,
                "password": credentials.password,
                "remember": True,
                "os": "web",
                "lang": self.language,
                "screen_width": 1920,
                "screen_height": 1080,
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-CSRF-TOKEN": csrf_token if csrf_token else "",
                "X-XSRF-TOKEN": xsrf_token if xsrf_token else "",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}{login_page_url}",
                "Origin": self.BASE_URL,
            },
        )
        logger.info(f"API login response: status={login_response.status_code}")

        # Check if API login was successful
        is_success = False
        if login_response.status_code == 200:
            try:
                api_data = login_response.json()
                is_success = api_data.get("status") == True
                logger.info(f"API login status: {api_data.get('status')}, message: {api_data.get('message')}")
            except Exception as e:
                logger.warning(f"Could not parse API login response: {e}")

        if is_success:
            # Log cookies received
            cookie_count = len(list(self.client.cookies.jar))
            logger.info(f"Login successful! Received {cookie_count} cookies")

            # Verify login by checking /api/address/view
            logger.info("Verifying login with /api/address/view...")
            try:
                verify_response = self.client.get("/api/address/view")
                if verify_response.status_code == 200:
                    verify_data = verify_response.json()
                    is_logged_in = verify_data.get("status") == True
                    logger.info(f"Login verification: status={verify_data.get('status')}, is_loggedin={is_logged_in}")

                    if not is_logged_in:
                        logger.error("Login verification FAILED - /api/address/view returned status:false")
                        return False

                    logger.info("✓ Login verification PASSED")
                else:
                    logger.warning(f"Login verification request failed with status: {verify_response.status_code}")
            except Exception as e:
                logger.error(f"Login verification error: {e}")
                return False

            self._save_cookies()
            self.auth_manager.session.user_email = credentials.email
            self.auth_manager.session.is_authenticated = True
            self.auth_manager._save_session()
            logger.info("Session saved successfully")
            return True

        # Login failed - log details for debugging
        logger.error(f"Login failed: API returned status=False")
        if login_response.status_code == 200:
            try:
                error_data = login_response.json()
                if error_data.get("errors"):
                    logger.error(f"API errors: {error_data.get('errors')}")
            except:
                pass

        return False

    def logout(self) -> None:
        """Logout from e-fresh.gr and clear session."""
        if self.auth_manager.is_authenticated():
            self._update_cookies()
            try:
                self.client.get(f"/{self.language}/account/logout")
            except Exception:
                pass  # Ignore errors during logout

        self.auth_manager.clear_session()
        self.client.cookies.clear()

    def search_products(
        self, query: Optional[str] = None, ean: Optional[str] = None
    ) -> list[Product]:
        """
        Search for products by name or EAN.

        Args:
            query: Product name or search term
            ean: EAN/barcode for exact match

        Returns:
            List of matching products

        Raises:
            ValueError: If neither query nor ean is provided
        """
        if not query and not ean:
            raise ValueError("Either query or ean must be provided")

        self._update_cookies()

        search_term = ean if ean else query

        # Use the /api/list endpoint with search query
        try:
            api_response = self.client.get(
                "/api/list",
                params={"q": search_term, "page": 1},
            )
            if api_response.status_code == 200:
                data = api_response.json()
                if data.get("status"):
                    products_data = data.get("data", {}).get("products", {}).get("data", [])
                    products = self._parse_products_from_api(products_data)

                    # If searching by EAN, filter for exact match
                    if ean:
                        products = [p for p in products if p.ean == ean]

                    return products
        except Exception as e:
            logger.error(f"Error searching products: {e}")

        return []

    def add_to_cart(self, product_id: str, quantity: int = 1) -> bool:
        """
        Add a product to the shopping cart.

        Args:
            product_id: Product ID
            quantity: Quantity to add

        Returns:
            True if successful

        Raises:
            Exception: If not authenticated or operation fails
        """
        logger.info(f"=== ADD TO CART: product_id={product_id}, quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            logger.error("ADD TO CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to modify cart")

        logger.info("Authenticated - updating cookies")
        self._update_cookies()

        # Log current cookies
        cookie_count = len(list(self.client.cookies.jar))
        logger.info(f"Active cookies: {cookie_count}")

        # Try API endpoint
        try:
            logger.info(f"Attempting API POST to /api/cart/add")
            response = self.client.post(
                f"/api/cart/add",
                json={"product_id": product_id, "quantity": quantity},
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"API Response: status={response.status_code}")

            if response.status_code in [200, 201]:
                try:
                    response_data = response.json()
                    logger.info(f"API Response data: status={response_data.get('status')}, message={response_data.get('message')}")
                    logger.info(f"API cart total_qty: {response_data.get('data', {}).get('cart', {}).get('total_qty', 'N/A')}")
                except:
                    logger.info(f"API Response text (first 200 chars): {response.text[:200]}")

                self._save_cookies()
                logger.info("ADD TO CART SUCCESS via API")
                return True
        except Exception as e:
            logger.warning(f"API add to cart failed: {e}")

        # Fallback to form submission
        logger.info(f"Fallback: Attempting form POST to /{self.language}/cart/add")
        response = self.client.post(
            f"/{self.language}/cart/add",
            data={"product_id": product_id, "quantity": quantity},
        )
        logger.info(f"Form Response: status={response.status_code}, url={response.url}")

        self._save_cookies()
        success = response.status_code in [200, 201, 302]
        logger.info(f"ADD TO CART {'SUCCESS' if success else 'FAILED'} via form (status: {response.status_code})")
        return success

    def remove_from_cart(self, product_id: str) -> bool:
        """
        Remove a product from the shopping cart.

        Args:
            product_id: Product ID to remove

        Returns:
            True if successful

        Raises:
            Exception: If not authenticated or operation fails
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        # Try API endpoint
        try:
            response = self.client.post(
                f"/api/cart/remove",
                json={"product_id": product_id},
                headers={"Content-Type": "application/json"},
            )
            if response.status_code in [200, 204]:
                self._save_cookies()
                return True
        except Exception:
            pass

        # Fallback to form submission
        response = self.client.post(
            f"/{self.language}/cart/remove", data={"product_id": product_id}
        )

        self._save_cookies()
        return response.status_code in [200, 204, 302]

    def update_cart_item_quantity(self, product_id: str, quantity: int) -> bool:
        """
        Update the quantity of a product in the shopping cart.

        Note: This uses the add_to_cart endpoint which sets (not adds to) the quantity.

        Args:
            product_id: Product ID to update
            quantity: New quantity to set

        Returns:
            True if successful

        Raises:
            Exception: If not authenticated or operation fails
        """
        logger.info(f"=== UPDATE CART: product_id={product_id}, new_quantity={quantity} ===")

        # add_to_cart actually SETS the quantity (doesn't add to existing)
        # so we can use it for updates
        return self.add_to_cart(product_id, quantity)

    def get_cart(self) -> Cart:
        """
        Get current shopping cart contents.

        Returns:
            Cart object with items and total

        Raises:
            Exception: If not authenticated
        """
        logger.info("=== GET CART ===")

        if not self.auth_manager.is_authenticated():
            logger.error("GET CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to view cart")

        logger.info("Authenticated - updating cookies")
        self._update_cookies()

        # Log current cookies
        cookie_count = len(list(self.client.cookies.jar))
        logger.info(f"Active cookies: {cookie_count}")

        # Try API endpoint
        try:
            logger.info("Attempting API GET to /api/cart")
            response = self.client.get(f"/api/cart")
            logger.info(f"API Response: status={response.status_code}")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"API Response: status={data.get('status')}, is_loggedin={data.get('is_loggedin')}")

                # Extract cart data from the response
                cart_data = data.get("data", {})
                logger.info(f"Cart data keys: {list(cart_data.keys())}")

                if "cart" in cart_data:
                    cart_info = cart_data["cart"]
                    logger.info(f"Cart info: total={cart_info.get('total')}, total_qty={cart_info.get('total_qty')}, items_count={len(cart_info.get('items', []))}")

                cart = self._parse_cart(cart_data)
                logger.info(f"Parsed cart: item_count={cart.item_count}, total={cart.total}, items={len(cart.items)}")
                return cart
        except Exception as e:
            logger.error(f"Error getting cart via API: {e}")
            import traceback
            logger.error(traceback.format_exc())

        # Fallback to web page
        logger.info(f"Fallback: Attempting GET to /{self.language}/cart")
        response = self.client.get(f"/{self.language}/cart")
        response.raise_for_status()
        logger.info(f"Cart page Response: status={response.status_code}")

        cart = self._parse_cart_from_html(response.text)
        logger.info(f"Parsed cart from HTML: item_count={cart.item_count}, total={cart.total}")
        return cart

    def get_orders(self, include_history: bool = True, include_items: bool = False) -> list[Order]:
        """
        Get user's orders.

        Args:
            include_history: If True, include past orders; if False, only current orders
            include_items: If True, fetch full order details including items for each order

        Returns:
            List of orders

        Raises:
            Exception: If not authenticated
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        # Try API endpoint with pagination
        try:
            all_orders = []
            page = 1
            max_pages = 50  # Safety limit to avoid infinite loops

            while page <= max_pages:
                # Use POST request like the website does (supports pagination)
                response = self.client.post(
                    "/api/account/orders",
                    json={
                        "page": page,
                        "os": "web",
                        "lang": self.language,
                        "screen_width": 1920,
                        "screen_height": 1080,
                    },
                    headers={"Content-Type": "application/json", "Accept": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    orders = self._parse_orders(data)

                    if not orders:
                        # No more orders, we've reached the end
                        break

                    all_orders.extend(orders)
                    logger.info(f"Fetched page {page}: {len(orders)} orders")

                    # Check if we got a full page - if not, this is the last page
                    orders_data = data.get("data", {}).get("orders", {})
                    per_page = orders_data.get("per_page", 10)
                    if len(orders) < per_page:
                        logger.info(f"Got less than {per_page} orders on page {page}, stopping pagination")
                        break

                    page += 1
                else:
                    logger.warning(f"Failed to fetch page {page}: status={response.status_code}")
                    break

            if all_orders:
                orders = all_orders

                if not include_history:
                    # Filter for active orders only
                    orders = [
                        o
                        for o in orders
                        if o.status.lower() in ["pending", "confirmed", "processing"]
                    ]

                # Optionally fetch full details with items for each order
                if include_items:
                    for order in orders:
                        try:
                            order_details = self.get_order_details(order.id)
                            if order_details and order_details.items:
                                order.items = order_details.items
                        except Exception as e:
                            logger.warning(f"Failed to fetch items for order {order.id}: {e}")

                logger.info(f"Returning {len(orders)} total orders")
                return orders
        except Exception as e:
            logger.error(f"Error fetching orders via API: {e}")

        # Fallback to web page
        logger.info("Falling back to HTML parsing")
        response = self.client.get(f"/{self.language}/account/orders")
        response.raise_for_status()

        orders = self._parse_orders_from_html(response.text)

        if not include_history:
            orders = [
                o for o in orders if o.status.lower() in ["pending", "confirmed", "processing"]
            ]

        return orders

    def get_order_details(self, order_id: str) -> Optional[Order]:
        """
        Get detailed information for a specific order, including items.

        Args:
            order_id: Order ID to fetch details for

        Returns:
            Order object with items, or None if order not found

        Raises:
            Exception: If not authenticated
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        # POST to /api/account/order with order ID in body
        try:
            response = self.client.post(
                "/api/account/order",
                json={
                    "id": order_id,
                    "os": "web",
                    "lang": self.language,
                    "screen_width": 1920,
                    "screen_height": 1080,
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status"):
                    order_data = data.get("data", {}).get("order", {})
                    # Parse the order details response
                    orders = self._parse_orders({"data": {"orders": {"data": [order_data]}}})
                    if orders:
                        return orders[0]
        except Exception as e:
            logger.error(f"Error fetching order details for {order_id}: {e}")

        return None

    # Helper methods for parsing responses

    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML."""
        # Try meta tag format: <meta name="csrf-token" content="...">
        match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        # Try input field format: name="csrf_token" value="..."
        match = re.search(r'name=["\']csrf_token["\'] value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        # Try JS object format: 'csrf_token': '...'
        match = re.search(r'["\']csrf_token["\']:\s*["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        return None

    def _parse_products_from_api(self, products_data: list[dict]) -> list[Product]:
        """Parse products from /api/list endpoint response."""
        products = []

        for item in products_data:
            try:
                # Extract maker from developer_id attribute
                maker = None
                if "attrs" in item and "developer_id" in item["attrs"]:
                    maker = item["attrs"]["developer_id"].get("title")

                # Get image URL
                image_url = None
                if "image" in item and item["image"].get("has_image"):
                    image_url = item["image"].get("url")

                # Get unit
                unit = None
                if "attrs" in item and "pkg_unit" in item["attrs"]:
                    unit = item["attrs"]["pkg_unit"].get("title")

                product = Product(
                    id=str(item.get("kodikos", item.get("id", ""))),
                    name=item.get("title", ""),
                    maker=maker,
                    ean=item.get("barcode"),  # EAN might not be in this endpoint
                    price=Decimal(str(item.get("price", 0))),
                    original_price=Decimal(str(item["price_old"]))
                    if item.get("price_old")
                    else None,
                    available=item.get("in_stock", True) and item.get("is_saleable", True),
                    image_url=image_url,
                    description=None,  # Not provided in list endpoint
                    unit=unit,
                )
                products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse product: {e}")
                continue

        return products

    def _parse_products_from_html(self, html: str) -> list[Product]:
        """Parse products from HTML response (fallback)."""
        # This is a simplified parser - in production, you'd use BeautifulSoup or similar
        products = []

        # Look for product data in JSON embedded in HTML
        json_match = re.search(r'products["\']?\s*:\s*(\[.*?\])', html, re.DOTALL)
        if json_match:
            try:
                import json

                products_data = json.loads(json_match.group(1))
                return self._parse_products(products_data)
            except Exception:
                pass

        return products

    def _parse_cart(self, data: Any) -> Cart:
        """Parse cart from API JSON response."""
        items = []
        # The cart data is nested in data.cart
        cart_data = data.get("cart", data)
        cart_items = cart_data.get("items", [])

        for item_data in cart_items:
            try:
                # Extract product info from the nested 'item' object
                product_info = item_data.get("item", {})

                # Get maker from attributes
                maker = None
                if "attrs" in product_info and "developer_id" in product_info["attrs"]:
                    maker = product_info["attrs"]["developer_id"].get("title")

                # Get image URL
                image_url = None
                if "image" in product_info and product_info["image"].get("has_image"):
                    image_url = product_info["image"].get("url")

                product = Product(
                    id=str(item_data.get("id", product_info.get("kodikos", ""))),
                    name=item_data.get("name", product_info.get("title", "")),
                    maker=maker,
                    ean=product_info.get("barcode"),
                    price=Decimal(str(item_data.get("price", 0))),
                    available=product_info.get("in_stock", True),
                    image_url=image_url,
                )

                cart_item = CartItem(
                    product=product,
                    quantity=item_data.get("qty", 1),
                    subtotal=Decimal(str(item_data.get("total", 0))),
                )
                items.append(cart_item)
            except Exception as e:
                logger.warning(f"Failed to parse cart item: {e}")
                continue

        return Cart(
            items=items,
            total=Decimal(str(cart_data.get("total", 0))),
            item_count=cart_data.get("total_qty", len(items)),
        )

    def _parse_cart_from_html(self, html: str) -> Cart:
        """Parse cart from HTML response (fallback)."""
        # Look for cart data in JSON embedded in HTML
        json_match = re.search(r'cart["\']?\s*:\s*(\{.*?\})', html, re.DOTALL)
        if json_match:
            try:
                import json

                cart_data = json.loads(json_match.group(1))
                return self._parse_cart(cart_data)
            except Exception:
                pass

        return Cart()

    def _parse_orders(self, data: Any) -> list[Order]:
        """Parse orders from API JSON response."""
        orders = []

        # Handle different response structures
        if isinstance(data, list):
            order_items = data
        elif "data" in data and "orders" in data["data"]:
            # API response: {data: {orders: {data: [...]}}}
            orders_obj = data["data"]["orders"]
            if isinstance(orders_obj, dict) and "data" in orders_obj:
                order_items = orders_obj["data"]
            else:
                order_items = orders_obj
        else:
            order_items = data.get("orders", [])

        for order_data in order_items:
            try:
                # Parse order items if available
                # Check both 'items' (list endpoint) and 'order_items' (details endpoint)
                items = []
                items_list = order_data.get("order_items", order_data.get("items", []))

                for item_data in items_list:
                    # Handle different field names from list vs details endpoints
                    product_name = (
                        item_data.get("title") or  # details endpoint
                        item_data.get("product_name") or  # list endpoint
                        item_data.get("name", "Unknown")
                    )

                    order_item = OrderItem(
                        product_name=product_name,
                        quantity=item_data.get("quantity", item_data.get("qty", 1)),
                        price=Decimal(str(item_data.get("price", 0))),
                        subtotal=Decimal(str(item_data.get("subtotal", item_data.get("total", 0)))),
                    )
                    items.append(order_item)

                # Parse created_at - handle different datetime formats
                created_at_str = order_data.get("created_at", "")
                if created_at_str:
                    # Remove timezone info if present, then parse
                    created_at_str = created_at_str.replace("Z", "+00:00")
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                    except:
                        # Fallback: try parsing without timezone
                        created_at = datetime.strptime(created_at_str.split("+")[0].strip(), "%Y-%m-%d %H:%M:%S")
                else:
                    created_at = datetime.now()

                # Parse delivery_date if present
                delivery_date = None
                if order_data.get("delivery_date"):
                    try:
                        delivery_date = datetime.fromisoformat(
                            order_data["delivery_date"].replace("Z", "+00:00")
                        )
                    except:
                        pass

                order = Order(
                    id=str(order_data.get("order_id", order_data.get("id", ""))),
                    order_number=str(order_data.get("order_id", order_data.get("order_number", order_data.get("id", "")))),
                    status=order_data.get("status", "unknown"),
                    created_at=created_at,
                    total=Decimal(str(order_data.get("total_amount", order_data.get("total", 0)))),
                    items=items,
                    delivery_address=order_data.get("delivery_address"),
                    delivery_date=delivery_date,
                )
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to parse order: {e}")
                continue

        return orders

    def _parse_orders_from_html(self, html: str) -> list[Order]:
        """Parse orders from HTML response (fallback)."""
        # Look for orders data in JSON embedded in HTML
        json_match = re.search(r'orders["\']?\s*:\s*(\[.*?\])', html, re.DOTALL)
        if json_match:
            try:
                import json

                orders_data = json.loads(json_match.group(1))
                return self._parse_orders(orders_data)
            except Exception:
                pass

        return []

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
