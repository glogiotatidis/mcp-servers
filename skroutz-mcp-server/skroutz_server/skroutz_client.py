"""Skroutz.gr API client."""

import logging
import re
from decimal import Decimal
from typing import Any, Optional
from datetime import datetime

import httpx
from .auth import AuthManager
from .models import AuthCredentials, Cart, CartItem, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class SkroutzClient:
    """Client for interacting with skroutz.gr."""

    BASE_URL = "https://www.skroutz.gr"

    def __init__(self, auth_manager: AuthManager) -> None:
        """
        Initialize the Skroutz client.

        Args:
            auth_manager: Authentication manager instance
        """
        self.auth_manager = auth_manager
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
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
        cookies = {}
        for cookie in self.client.cookies.jar:
            cookies[cookie.name] = cookie.value
        if cookies:
            self.auth_manager.save_session(
                cookies=cookies, user_email=self.auth_manager.session.user_email
            )

    async def login(self, credentials: AuthCredentials) -> bool:
        """
        Authenticate with skroutz.gr.

        Args:
            credentials: User credentials (email and password)

        Returns:
            True if login successful, False otherwise
        """
        logger.info(f"=== LOGIN: email={credentials.email} ===")

        try:
            # Get the login page to retrieve CSRF token and session cookies
            logger.info("Getting login page...")
            response = self.client.get("/login")
            response.raise_for_status()
            logger.info(f"Login page response: status={response.status_code}")

            # Extract CSRF token from page
            csrf_token = self._extract_csrf_token(response.text)
            logger.info(f"CSRF token: {'Found' if csrf_token else 'Not found'}")

            # Prepare login payload
            login_data = {
                "username": credentials.email,
                "password": credentials.password,
                "remember_me": "1",
            }

            if csrf_token:
                login_data["authenticity_token"] = csrf_token

            # Submit login form
            logger.info("Submitting login form...")
            login_response = self.client.post(
                "/login",
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{self.BASE_URL}/login",
                    "Origin": self.BASE_URL,
                },
            )
            logger.info(f"Login response: status={login_response.status_code}, url={login_response.url}")

            # Check if login was successful
            # Usually successful login redirects to homepage or user area
            is_success = False

            # Check for redirect to user area or homepage (not back to login)
            if login_response.status_code in [200, 302] and "/login" not in str(login_response.url):
                # Verify by checking if we can access a protected page
                logger.info("Verifying login by accessing user area...")
                verify_response = self.client.get("/account")

                if verify_response.status_code == 200:
                    # Check if the response contains user-specific content
                    if "logout" in verify_response.text.lower() or "account" in verify_response.text.lower():
                        is_success = True
                        logger.info("✓ Login verification PASSED")

            if is_success:
                cookie_count = len(list(self.client.cookies.jar))
                logger.info(f"Login successful! Received {cookie_count} cookies")

                self._save_cookies()
                self.auth_manager.session.user_email = credentials.email
                self.auth_manager.session.is_authenticated = True
                self.auth_manager._save_session()
                logger.info("Session saved successfully")
                return True
            else:
                logger.error("Login failed: Could not verify successful authentication")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return False

    def logout(self) -> None:
        """Logout from skroutz.gr and clear session."""
        if self.auth_manager.is_authenticated():
            self._update_cookies()
            try:
                self.client.get("/logout")
            except Exception:
                pass  # Ignore errors during logout

        self.auth_manager.clear_session()
        self.client.cookies.clear()
        logger.info("Logged out successfully")

    def search_products(self, query: str) -> list[Product]:
        """
        Search for products by name.

        Args:
            query: Product name or search term

        Returns:
            List of matching products
        """
        logger.info(f"=== SEARCH: query='{query}' ===")

        try:
            # Skroutz search URL
            search_response = self.client.get(
                "/search",
                params={"keyphrase": query},
            )
            search_response.raise_for_status()

            # Parse products from search results
            products = self._parse_products_from_html(search_response.text)
            logger.info(f"Found {len(products)} products")

            return products

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return []

    def add_to_cart(self, product_id: str, quantity: int = 1) -> bool:
        """
        Add a product to the shopping cart.

        Args:
            product_id: Product ID
            quantity: Quantity to add

        Returns:
            True if successful
        """
        logger.info(f"=== ADD TO CART: product_id={product_id}, quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            logger.error("ADD TO CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            # Add to cart (will need to find actual endpoint)
            response = self.client.post(
                "/cart/add",
                data={"product_id": product_id, "quantity": quantity},
            )

            if response.status_code in [200, 201, 302]:
                self._save_cookies()
                logger.info("ADD TO CART SUCCESS")
                return True

            logger.error(f"ADD TO CART FAILED: status={response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Add to cart error: {e}", exc_info=True)
            return False

    def remove_from_cart(self, product_id: str) -> bool:
        """
        Remove a product from the shopping cart.

        Args:
            product_id: Product ID to remove

        Returns:
            True if successful
        """
        logger.info(f"=== REMOVE FROM CART: product_id={product_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            response = self.client.post(
                "/cart/remove",
                data={"product_id": product_id},
            )

            if response.status_code in [200, 204, 302]:
                self._save_cookies()
                logger.info("REMOVE FROM CART SUCCESS")
                return True

            logger.error(f"REMOVE FROM CART FAILED: status={response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Remove from cart error: {e}", exc_info=True)
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
        logger.info(f"=== UPDATE CART: product_id={product_id}, new_quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            response = self.client.post(
                "/cart/update",
                data={"product_id": product_id, "quantity": quantity},
            )

            if response.status_code in [200, 201, 302]:
                self._save_cookies()
                logger.info("UPDATE CART SUCCESS")
                return True

            logger.error(f"UPDATE CART FAILED: status={response.status_code}")
            return False

        except Exception as e:
            logger.error(f"Update cart error: {e}", exc_info=True)
            return False

    def get_cart(self) -> Cart:
        """
        Get current shopping cart contents.

        Returns:
            Cart object with items and total
        """
        logger.info("=== GET CART ===")

        if not self.auth_manager.is_authenticated():
            logger.error("GET CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to view cart")

        self._update_cookies()

        try:
            response = self.client.get("/cart")
            response.raise_for_status()

            cart = self._parse_cart_from_html(response.text)
            logger.info(f"Cart: item_count={cart.item_count}, total={cart.total}")

            return cart

        except Exception as e:
            logger.error(f"Get cart error: {e}", exc_info=True)
            return Cart()

    def get_orders(self, include_history: bool = True) -> list[Order]:
        """
        Get user's orders.

        Args:
            include_history: If True, include past orders; if False, only current orders

        Returns:
            List of orders
        """
        logger.info("=== GET ORDERS ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        try:
            response = self.client.get("/account/orders")
            response.raise_for_status()

            orders = self._parse_orders_from_html(response.text)
            logger.info(f"Found {len(orders)} orders")

            if not include_history:
                orders = [
                    o
                    for o in orders
                    if o.status.lower() in ["pending", "confirmed", "processing"]
                ]

            return orders

        except Exception as e:
            logger.error(f"Get orders error: {e}", exc_info=True)
            return []

    def get_order_details(self, order_id: str) -> Optional[Order]:
        """
        Get detailed information for a specific order, including items.

        Args:
            order_id: Order ID to fetch details for

        Returns:
            Order object with items, or None if order not found
        """
        logger.info(f"=== GET ORDER DETAILS: order_id={order_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        try:
            response = self.client.get(f"/account/orders/{order_id}")
            response.raise_for_status()

            order = self._parse_order_details_from_html(response.text, order_id)
            logger.info(f"Order details retrieved for {order_id}")

            return order

        except Exception as e:
            logger.error(f"Get order details error: {e}", exc_info=True)
            return None

    # Helper methods for parsing responses

    def _extract_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML."""
        # Try meta tag format
        match = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)

        # Try input field format
        match = re.search(r'name=["\']authenticity_token["\'] value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)

        # Try Rails CSRF token
        match = re.search(r'name=["\']csrf[_-]token["\'] value=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _parse_products_from_html(self, html: str) -> list[Product]:
        """Parse products from HTML response."""
        from bs4 import BeautifulSoup

        products = []
        soup = BeautifulSoup(html, 'lxml')

        # Skroutz typically uses product cards or list items
        # This is a generic parser - will need adjustment based on actual HTML structure
        product_elements = soup.find_all(['li', 'div'], class_=re.compile(r'product|item', re.I))

        for elem in product_elements[:50]:  # Limit to first 50 products
            try:
                # Extract product information
                name_elem = elem.find(['a', 'h2', 'h3', 'h4'], class_=re.compile(r'name|title', re.I))
                price_elem = elem.find(['span', 'div'], class_=re.compile(r'price', re.I))
                image_elem = elem.find('img')
                link_elem = elem.find('a', href=True)

                if not name_elem:
                    continue

                name = name_elem.get_text(strip=True)
                product_id = ""
                price_text = ""

                if price_elem:
                    price_text = price_elem.get_text(strip=True)

                if link_elem:
                    href = link_elem.get('href', '')
                    # Skroutz uses /s/{sku_id}/ format
                    id_match = re.search(r'/s/(\d+)', href)
                    if id_match:
                        product_id = id_match.group(1)

                # Parse price
                price = Decimal("0")
                if price_text:
                    # Remove currency symbols and extract number
                    price_match = re.search(r'(\d+[.,]\d+)', price_text.replace('.', '').replace(',', '.'))
                    if price_match:
                        price = Decimal(price_match.group(1))

                product = Product(
                    id=product_id or f"unknown_{len(products)}",
                    name=name,
                    price=price,
                    available=True,
                    image_url=image_elem.get('src') if image_elem else None,
                    url=f"{self.BASE_URL}{link_elem.get('href')}" if link_elem and link_elem.get('href') else None,
                )
                products.append(product)

            except Exception as e:
                logger.warning(f"Failed to parse product: {e}")
                continue

        return products

    def _parse_cart_from_html(self, html: str) -> Cart:
        """Parse cart from HTML response."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        items = []
        total = Decimal("0")

        # Parse cart items (structure will vary)
        cart_items = soup.find_all(['div', 'li'], class_=re.compile(r'cart.*item', re.I))

        for item_elem in cart_items:
            try:
                name_elem = item_elem.find(['a', 'span', 'h3'], class_=re.compile(r'name|title', re.I))
                price_elem = item_elem.find(['span', 'div'], class_=re.compile(r'price', re.I))
                qty_elem = item_elem.find(['input', 'span'], class_=re.compile(r'quantity|qty', re.I))

                if not name_elem:
                    continue

                name = name_elem.get_text(strip=True)
                quantity = 1
                price = Decimal("0")

                if qty_elem:
                    qty_text = qty_elem.get('value') or qty_elem.get_text(strip=True)
                    try:
                        quantity = int(qty_text)
                    except:
                        pass

                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d+[.,]\d+)', price_text.replace('.', '').replace(',', '.'))
                    if price_match:
                        price = Decimal(price_match.group(1))

                product = Product(
                    id=f"cart_item_{len(items)}",
                    name=name,
                    price=price,
                    available=True,
                )

                cart_item = CartItem(
                    product=product,
                    quantity=quantity,
                    subtotal=price * quantity,
                )
                items.append(cart_item)

            except Exception as e:
                logger.warning(f"Failed to parse cart item: {e}")
                continue

        # Parse total
        total_elem = soup.find(['span', 'div'], class_=re.compile(r'total', re.I))
        if total_elem:
            total_text = total_elem.get_text(strip=True)
            total_match = re.search(r'(\d+[.,]\d+)', total_text.replace('.', '').replace(',', '.'))
            if total_match:
                total = Decimal(total_match.group(1))

        return Cart(
            items=items,
            total=total,
            item_count=sum(item.quantity for item in items),
        )

    def _parse_orders_from_html(self, html: str) -> list[Order]:
        """Parse orders from HTML response."""
        from bs4 import BeautifulSoup

        orders = []
        soup = BeautifulSoup(html, 'lxml')

        # Parse order elements
        order_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'order', re.I))

        for order_elem in order_elements:
            try:
                order_id = ""
                order_number = ""
                status = "unknown"
                created_at = datetime.now()
                total = Decimal("0")

                # Extract order details
                id_elem = order_elem.find(['span', 'a'], class_=re.compile(r'order.*id|number', re.I))
                if id_elem:
                    order_text = id_elem.get_text(strip=True)
                    id_match = re.search(r'(\d+)', order_text)
                    if id_match:
                        order_id = id_match.group(1)
                        order_number = order_id

                status_elem = order_elem.find(['span', 'div'], class_=re.compile(r'status', re.I))
                if status_elem:
                    status = status_elem.get_text(strip=True).lower()

                date_elem = order_elem.find(['span', 'div', 'time'], class_=re.compile(r'date|created', re.I))
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    # Try to parse date
                    try:
                        created_at = datetime.strptime(date_text, '%d/%m/%Y')
                    except:
                        pass

                total_elem = order_elem.find(['span', 'div'], class_=re.compile(r'total|amount', re.I))
                if total_elem:
                    total_text = total_elem.get_text(strip=True)
                    total_match = re.search(r'(\d+[.,]\d+)', total_text.replace('.', '').replace(',', '.'))
                    if total_match:
                        total = Decimal(total_match.group(1))

                if order_id:
                    order = Order(
                        id=order_id,
                        order_number=order_number,
                        status=status,
                        created_at=created_at,
                        total=total,
                    )
                    orders.append(order)

            except Exception as e:
                logger.warning(f"Failed to parse order: {e}")
                continue

        return orders

    def _parse_order_details_from_html(self, html: str, order_id: str) -> Optional[Order]:
        """Parse order details from HTML response."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        items = []

        # Parse order items
        item_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'item|product', re.I))

        for item_elem in item_elements:
            try:
                name_elem = item_elem.find(['a', 'span', 'td'], class_=re.compile(r'name|title', re.I))
                if not name_elem:
                    continue

                product_name = name_elem.get_text(strip=True)
                quantity = 1
                price = Decimal("0")
                subtotal = Decimal("0")

                qty_elem = item_elem.find(['span', 'td'], class_=re.compile(r'quantity|qty', re.I))
                if qty_elem:
                    qty_text = qty_elem.get_text(strip=True)
                    try:
                        quantity = int(re.search(r'\d+', qty_text).group())
                    except:
                        pass

                price_elem = item_elem.find(['span', 'td'], class_=re.compile(r'price', re.I))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d+[.,]\d+)', price_text.replace('.', '').replace(',', '.'))
                    if price_match:
                        price = Decimal(price_match.group(1))
                        subtotal = price * quantity

                order_item = OrderItem(
                    product_name=product_name,
                    quantity=quantity,
                    price=price,
                    subtotal=subtotal,
                )
                items.append(order_item)

            except Exception as e:
                logger.warning(f"Failed to parse order item: {e}")
                continue

        # Create order object
        # Extract order info from page
        order_number = order_id
        status = "unknown"
        created_at = datetime.now()
        total = Decimal("0")

        # Parse order metadata
        status_elem = soup.find(['span', 'div'], class_=re.compile(r'status', re.I))
        if status_elem:
            status = status_elem.get_text(strip=True).lower()

        total_elem = soup.find(['span', 'div'], class_=re.compile(r'total', re.I))
        if total_elem:
            total_text = total_elem.get_text(strip=True)
            total_match = re.search(r'(\d+[.,]\d+)', total_text.replace('.', '').replace(',', '.'))
            if total_match:
                total = Decimal(total_match.group(1))

        return Order(
            id=order_id,
            order_number=order_number,
            status=status,
            created_at=created_at,
            total=total,
            items=items,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
