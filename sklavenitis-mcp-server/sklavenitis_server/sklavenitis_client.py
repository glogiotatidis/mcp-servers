"""Sklavenitis.gr API client."""

import logging
import re
from decimal import Decimal
from typing import Any, Optional
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from .auth import AuthManager
from .models import AuthCredentials, Cart, CartItem, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class SklavenitisClient:
    """Client for interacting with sklavenitis.gr."""

    BASE_URL = "https://www.sklavenitis.gr"

    def __init__(self, auth_manager: AuthManager, language: str = "el") -> None:
        """
        Initialize the sklavenitis client.

        Args:
            auth_manager: Authentication manager instance
            language: Language code (el for Greek, en for English)
        """
        self.auth_manager = auth_manager
        self.language = language
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=30.0,
            follow_redirects=False,  # Disable auto-redirect to capture cookies properly
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": f"{language}-GR,{language};q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    def _update_cookies(self) -> None:
        """Update client cookies from auth manager."""
        cookies = self.auth_manager.get_cookies()
        self.client.cookies.clear()
        for name, value in cookies.items():
            self.client.cookies.set(name, value)

        # Ensure Zone cookie is set (required for cart operations)
        # If not present in saved cookies, set a default
        if 'Zone' not in cookies:
            import json
            self.client.cookies.set('Zone', json.dumps({"ShippingType": 1, "HubID": 9}))

    def _save_cookies(self, response: Optional[httpx.Response] = None) -> None:
        """Save current cookies to auth manager."""
        cookies = {}

        # Get cookies from jar (non HTTP-only)
        for cookie in self.client.cookies.jar:
            cookies[cookie.name] = cookie.value

        # Also extract cookies from response Set-Cookie headers (including HTTP-only)
        if response:
            from http.cookies import SimpleCookie
            set_cookie_headers = response.headers.get_list('set-cookie')
            logger.info(f"Found {len(set_cookie_headers)} Set-Cookie headers in response")
            for set_cookie_header in set_cookie_headers:
                logger.info(f"Set-Cookie: {set_cookie_header[:100]}")
                cookie = SimpleCookie()
                cookie.load(set_cookie_header)
                for key, morsel in cookie.items():
                    cookies[key] = morsel.value
                    logger.info(f"Extracted cookie: {key}={morsel.value[:50] if len(morsel.value) > 50 else morsel.value}")

        if cookies:
            self.auth_manager.save_session(
                cookies=cookies, user_email=self.auth_manager.session.user_email
            )

    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract __RequestVerificationToken from HTML."""
        match = re.search(
            r'<input name="__RequestVerificationToken" type="hidden" value="([^"]+)"',
            html
        )
        if match:
            return match.group(1)
        return None

    async def login(self, credentials: AuthCredentials) -> bool:
        """
        Authenticate with sklavenitis.gr.

        Args:
            credentials: User credentials (email and password)

        Returns:
            True if login successful, False otherwise
        """
        logger.info(f"=== LOGIN: email={credentials.email} ===")

        # Step 1: Visit homepage to establish session
        logger.info("Visiting homepage to establish session...")
        response = self.client.get("/")
        response.raise_for_status()
        logger.info(f"Homepage response: status={response.status_code}")

        # Step 2: Get login form with returnUrl
        return_url = "/account/prosopika-stoiheia"
        logger.info(f"Getting login form with returnUrl={return_url}...")
        response = self.client.get(
            f"/{self.language}/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/?returnUrl={return_url}",
            headers={"Referer": self.BASE_URL + "/"}
        )
        response.raise_for_status()
        logger.info(f"Login form response: status={response.status_code}")

        # Extract CSRF token
        csrf_token = self._extract_csrf_token(response.text)
        if not csrf_token:
            logger.error("Failed to extract CSRF token from login form")
            return False
        logger.info("CSRF token extracted successfully")

        # Step 3: Submit login form
        logger.info("Submitting login form...")
        login_data = {
            "__RequestVerificationToken": csrf_token,
            "FormName": "Login",
            "Email": credentials.email,
            "Password": credentials.password,
            "RememberMe": "true",
        }

        login_response = self.client.post(
            f"/{self.language}/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/?returnUrl={return_url}",
            data=login_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": self.BASE_URL + "/",
                "Origin": self.BASE_URL,
            },
        )
        logger.info(f"Login POST response: status={login_response.status_code}")
        logger.info(f"Login response Set-Cookie headers: {login_response.headers.get_list('set-cookie')}")
        logger.info(f"Login response all cookies in jar: {[c.name for c in self.client.cookies.jar]}")

        # Step 4: Verify login by accessing account page
        logger.info("Verifying login by accessing account page...")
        verify_response = self.client.get("/account/prosopika-stoiheia")
        logger.info(f"Account page response: status={verify_response.status_code}")

        # Check for logged-in indicators
        is_logged_in = (
            "logout" in verify_response.text.lower() or
            "αποσύνδεση" in verify_response.text.lower()
        )

        if is_logged_in:
            logger.info("✓ Login successful - found logout button")
            # Save cookies from login response (includes HTTP-only cookies like .AspNet.ApplicationCookie_Frontend4 and Zone)
            self._save_cookies(login_response)
            self.auth_manager.session.user_email = credentials.email
            self.auth_manager.session.is_authenticated = True
            self.auth_manager._save_session()
            return True
        else:
            logger.error("✗ Login failed - no logout button found")
            return False

    def logout(self) -> None:
        """Logout from sklavenitis.gr and clear session."""
        if self.auth_manager.is_authenticated():
            self._update_cookies()
            try:
                self.client.post(
                    "/ajax/Atcom.Sites.Yoda.Components.Account.LogOut/",
                    headers={"Referer": self.BASE_URL + "/"}
                )
            except Exception as e:
                logger.warning(f"Error during logout: {e}")

        self.auth_manager.clear_session()
        self.client.cookies.clear()
        logger.info("Logged out successfully")

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
        """
        if not query and not ean:
            raise ValueError("Either query or ean must be provided")

        self._update_cookies()
        search_term = ean if ean else query

        try:
            # Use AJAX search endpoint which returns full product data with prices and IDs
            response = self.client.get(
                "/ajax/Atcom.Sites.Yoda.Components.Search.Index/",
                params={"Query": search_term},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if response.status_code == 200:
                return self._parse_products_from_ajax_search(response.text)

        except Exception as e:
            logger.error(f"Error searching products: {e}")

        return []

    def get_cart(self) -> Cart:
        """
        Get current shopping cart contents.

        Returns:
            Cart object with items and total
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view cart")

        self._update_cookies()

        try:
            # Get mini cart view
            response = self.client.get(
                "/ajax/Atcom.Sites.Yoda.Components.Cart.Index/?View=MiniCart"
            )
            if response.status_code == 200:
                return self._parse_cart_from_html(response.text)
        except Exception as e:
            logger.error(f"Error getting cart: {e}")

        return Cart()

    def set_delivery_timeslot(self, start_time: str, end_time: str) -> bool:
        """
        Set delivery timeslot (required before adding items to cart).

        Args:
            start_time: Start time in format "YYYY-MM-DD HH:MM:SS"
            end_time: End time in format "YYYY-MM-DD HH:MM:SS"

        Returns:
            True if successful
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to set delivery timeslot")

        self._update_cookies()

        try:
            response = self.client.post(
                "/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/",
                data={
                    "TimeSlotDate": start_time,
                    "TimeSlotDateTo": end_time,
                    "RequiresNotification": "False",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": self.BASE_URL + "/",
                },
            )
            success = response.status_code in [200, 201]
            if success:
                self._save_cookies(response)
                logger.info(f"✓ Delivery timeslot set: {start_time} - {end_time}")
            return success
        except Exception as e:
            logger.error(f"Error setting delivery timeslot: {e}")
            return False

    def add_to_cart(self, product_id: str, quantity: int = 1) -> bool:
        """
        Add a product to the shopping cart.

        Note: Requires delivery timeslot to be set first using set_delivery_timeslot().

        Args:
            product_id: Product ID (ProductSKU)
            quantity: Quantity to add (in grams for weighted items, units for countable items)

        Returns:
            True if successful
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            # Use CartItems array format with required headers (from HAR analysis)
            response = self.client.post(
                f"/{self.language}/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/",
                data={
                    "Action": "Update",
                    "CartItems[0][ProductSKU]": product_id,
                    "CartItems[0][Quantity]": str(quantity),
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-UserFlow-New": "true",
                    "AnalyticsTracker-Enabled": "true",
                    "Origin": self.BASE_URL,
                    "Referer": self.BASE_URL + "/",
                },
            )
            logger.info(f"Add to cart response: status={response.status_code}")
            logger.info(f"Response body: {response.text[:500]}")
            logger.info(f"Response headers: {dict(response.headers)}")
            success = response.status_code in [200, 201]
            if success:
                self._save_cookies(response)
            return success
        except Exception as e:
            logger.error(f"Error adding to cart: {e}")
            return False

    def remove_from_cart(self, product_id: str) -> bool:
        """
        Remove a product from the shopping cart.

        Args:
            product_id: Product ID to remove

        Returns:
            True if successful
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            response = self.client.post(
                "/ajax/Atcom.Sites.Yoda.Components.Cart.RemoveItem/",
                data={"productId": product_id},
            )
            success = response.status_code in [200, 204]
            if success:
                self._save_cookies()
            return success
        except Exception as e:
            logger.error(f"Error removing from cart: {e}")
            return False

    def update_cart_item_quantity(self, product_id: str, quantity: int) -> bool:
        """
        Update the quantity of a product in the shopping cart.

        Args:
            product_id: Product ID to update
            quantity: New quantity to set

        Returns:
            True if successful
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            response = self.client.post(
                "/ajax/Atcom.Sites.Yoda.Components.Cart.UpdateQuantity/",
                data={"productId": product_id, "quantity": quantity},
            )
            success = response.status_code in [200, 201]
            if success:
                self._save_cookies()
            return success
        except Exception as e:
            logger.error(f"Error updating cart quantity: {e}")
            return False

    def get_orders(self, include_history: bool = True) -> list[Order]:
        """
        Get user's orders.

        Args:
            include_history: If True, include past orders

        Returns:
            List of orders
        """
        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        try:
            response = self.client.get("/account/paraggelvies")
            if response.status_code == 200:
                return self._parse_orders_from_html(response.text)
        except Exception as e:
            logger.error(f"Error getting orders: {e}")

        return []

    # Helper methods for parsing responses

    def _parse_products_from_ajax_search(self, html: str) -> list[Product]:
        """Parse products from AJAX search results with full data."""
        products = []
        soup = BeautifulSoup(html, 'html.parser')

        # Find all product containers with analytics data
        product_containers = soup.find_all(attrs={"data-plugin-analyticsimpressions": True})

        for container in product_containers:
            try:
                # Extract JSON analytics data which has complete product info
                analytics_json = container.get("data-plugin-analyticsimpressions", "")
                if analytics_json:
                    import json
                    analytics_data = json.loads(analytics_json)
                    items = analytics_data.get("Call", {}).get("ecommerce", {}).get("items", [])

                    for item in items:
                        # Extract product ID from URL in the container
                        link = container.find("a", href=True)
                        product_id = item.get("item_id", "")

                        # If no item_id in analytics, try to extract from URL
                        if not product_id and link:
                            # URL format: /path/to/product-name-{id}/
                            url = link["href"]
                            id_match = re.search(r'-(\d+)/?$', url)
                            if id_match:
                                product_id = id_match.group(1)

                        product = Product(
                            id=str(product_id),
                            name=item.get("item_name", ""),
                            maker=item.get("item_brand"),
                            price=Decimal(str(item.get("price", 0))),
                            available=True,
                        )
                        products.append(product)

            except Exception as e:
                logger.warning(f"Failed to parse product from analytics data: {e}")
                continue

        return products

    def _parse_products_from_autocomplete(self, data: list[dict]) -> list[Product]:
        """Parse products from autocomplete JSON response."""
        products = []
        for item in data:
            try:
                product = Product(
                    id=str(item.get("id", "")),
                    name=item.get("label", ""),
                    price=Decimal(str(item.get("price", 0))),
                    available=True,
                    image_url=item.get("image"),
                )
                products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse product from autocomplete: {e}")
                continue
        return products

    def _parse_products_from_html(self, html: str) -> list[Product]:
        """Parse products from HTML search results."""
        products = []
        soup = BeautifulSoup(html, 'html.parser')

        # Find product elements
        product_els = soup.find_all(attrs={"data-product-id": True})

        for el in product_els:
            try:
                product_id = el.get("data-product-id")
                name_el = el.find(class_=re.compile("product.*name", re.I))
                price_el = el.find(class_=re.compile("product.*price", re.I))

                product = Product(
                    id=product_id,
                    name=name_el.get_text(strip=True) if name_el else "Unknown",
                    price=Decimal(
                        re.sub(r"[^\d.,]", "", price_el.get_text(strip=True))
                        .replace(",", ".")
                    ) if price_el else Decimal("0"),
                    available=True,
                )
                products.append(product)
            except Exception as e:
                logger.warning(f"Failed to parse product from HTML: {e}")
                continue

        return products

    def _parse_cart_from_html(self, html: str) -> Cart:
        """Parse cart from HTML response."""
        cart = Cart()
        soup = BeautifulSoup(html, 'html.parser')

        # Find cart items
        item_els = soup.find_all(attrs={"data-cart-item-id": True})

        for el in item_els:
            try:
                product_id = el.get("data-product-id")
                name_el = el.find(class_=re.compile("product.*name", re.I))
                price_el = el.find(class_=re.compile("product.*price", re.I))
                qty_el = el.find("input", attrs={"name": re.compile("quantity", re.I)})

                quantity = int(qty_el.get("value", 1)) if qty_el else 1
                price = Decimal(
                    re.sub(r"[^\d.,]", "", price_el.get_text(strip=True))
                    .replace(",", ".")
                ) if price_el else Decimal("0")

                product = Product(
                    id=product_id,
                    name=name_el.get_text(strip=True) if name_el else "Unknown",
                    price=price,
                    available=True,
                )

                cart_item = CartItem(
                    product=product,
                    quantity=quantity,
                    subtotal=price * quantity,
                )
                cart.items.append(cart_item)
                cart.total += cart_item.subtotal
                cart.item_count += quantity

            except Exception as e:
                logger.warning(f"Failed to parse cart item: {e}")
                continue

        return cart

    def _parse_orders_from_html(self, html: str) -> list[Order]:
        """Parse orders from HTML response."""
        orders = []
        soup = BeautifulSoup(html, 'html.parser')

        # Find order elements
        order_els = soup.find_all(attrs={"data-order-id": True})

        for el in order_els:
            try:
                order_id = el.get("data-order-id")
                order_number_el = el.find(class_=re.compile("order.*number", re.I))
                status_el = el.find(class_=re.compile("order.*status", re.I))
                date_el = el.find(class_=re.compile("order.*date", re.I))
                total_el = el.find(class_=re.compile("order.*total", re.I))

                order = Order(
                    id=order_id,
                    order_number=order_number_el.get_text(strip=True) if order_number_el else order_id,
                    status=status_el.get_text(strip=True) if status_el else "unknown",
                    created_at=datetime.now(),  # Would need proper date parsing
                    total=Decimal(
                        re.sub(r"[^\d.,]", "", total_el.get_text(strip=True))
                        .replace(",", ".")
                    ) if total_el else Decimal("0"),
                )
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to parse order: {e}")
                continue

        return orders

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
