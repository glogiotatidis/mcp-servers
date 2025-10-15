"""Skroutz.gr client using curl_cffi for Cloudflare bypass."""

import logging
import re
from decimal import Decimal
from typing import Any, Optional
from datetime import datetime

from curl_cffi import requests
from .auth import AuthManager
from .models import AuthCredentials, Cart, CartItem, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class SkroutzClientCffi:
    """Client for interacting with skroutz.gr using curl_cffi for CF bypass."""

    BASE_URL = "https://www.skroutz.gr"

    def __init__(self, auth_manager: AuthManager) -> None:
        """
        Initialize the Skroutz client with curl_cffi.

        Args:
            auth_manager: Authentication manager instance
        """
        self.auth_manager = auth_manager
        # Create a session that impersonates Chrome browser
        self.session = requests.Session(impersonate="chrome120")

        # Set realistic headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        })

        # Load existing cookies from auth manager
        self._update_cookies()

    def _update_cookies(self) -> None:
        """Update session cookies from auth manager."""
        cookies = self.auth_manager.get_cookies()
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".skroutz.gr")

    def _save_cookies(self) -> None:
        """Save current cookies to auth manager."""
        cookies = {}
        # curl_cffi cookies are already a dict-like object
        for name in self.session.cookies:
            cookies[name] = self.session.cookies[name]
        if cookies:
            self.auth_manager.save_session(
                cookies=cookies, user_email=self.auth_manager.session.user_email
            )

    def login(self, credentials: AuthCredentials) -> bool:
        """
        Authenticate with skroutz.gr using curl_cffi.

        Args:
            credentials: User credentials (email and password)

        Returns:
            True if login successful, False otherwise
        """
        logger.info(f"=== LOGIN (curl_cffi): email={credentials.email} ===")

        try:
            # Step 1: Get the login page to retrieve CSRF token
            logger.info("Getting login page...")
            response = self.session.get(
                f"{self.BASE_URL}/login",
                timeout=30,
                allow_redirects=True
            )

            logger.info(f"Login page response: status={response.status_code}")

            if response.status_code == 403:
                logger.error("403 Forbidden - Cloudflare may still be blocking")
                return False

            response.raise_for_status()

            # Extract CSRF token
            csrf_token = self._extract_csrf_token(response.text)
            logger.info(f"CSRF token: {'Found' if csrf_token else 'Not found'}")

            # Step 2: Submit email first (Skroutz uses username field for email)
            logger.info("Submitting email...")
            email_data = {
                "sign_in": "true",
                "user[username]": credentials.email,
            }
            if csrf_token:
                email_data["authenticity_token"] = csrf_token

            email_response = self.session.post(
                f"{self.BASE_URL}/login",
                data=email_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{self.BASE_URL}/login",
                    "Origin": self.BASE_URL,
                },
                timeout=30,
                allow_redirects=True
            )

            logger.info(f"Email step response: status={email_response.status_code}, url={email_response.url}")

            # Step 3: Check if we need to submit password (two-step flow)
            if email_response.status_code == 200 and "password" in email_response.text.lower():
                logger.info("Password page detected, submitting password...")

                # Extract new CSRF token from password page
                csrf_token = self._extract_csrf_token(email_response.text)

                password_data = {
                    "sign_in": "true",
                    "user[password]": credentials.password,
                    "user[remember_me]": "1",
                }
                if csrf_token:
                    password_data["authenticity_token"] = csrf_token

                login_response = self.session.post(
                    f"{self.BASE_URL}/login",
                    data=password_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": f"{self.BASE_URL}/login",
                        "Origin": self.BASE_URL,
                    },
                    timeout=30,
                    allow_redirects=True
                )
            else:
                # Use email response as login response if already redirected
                login_response = email_response

            logger.info(f"Login response: status={login_response.status_code}, url={login_response.url}")

            # Check if login was successful
            is_success = False

            # Check for redirect away from login page
            if login_response.status_code in [200, 302] and "/login" not in str(login_response.url):
                # Verify by checking if we can access user area
                logger.info("Verifying login by accessing user area...")
                verify_response = self.session.get(
                    f"{self.BASE_URL}/account",
                    timeout=30
                )

                if verify_response.status_code == 200:
                    # Check for logout link or user-specific content
                    content_lower = verify_response.text.lower()
                    if "logout" in content_lower or "αποσύνδεση" in content_lower or "λογαριασμός" in content_lower:
                        is_success = True
                        logger.info("✓ Login verification PASSED")

            if is_success:
                logger.info("Login successful!")
                self._save_cookies()
                self.auth_manager.session.user_email = credentials.email
                self.auth_manager.session.is_authenticated = True
                self.auth_manager._save_session()
                logger.info("Session saved successfully")
                return True
            else:
                logger.error("Login failed: Could not verify successful authentication")
                # Log response content for debugging
                if login_response.status_code == 403:
                    logger.error("Got 403 - likely still being blocked by Cloudflare")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return False

    def logout(self) -> None:
        """Logout from skroutz.gr and clear session."""
        if self.auth_manager.is_authenticated():
            self._update_cookies()
            try:
                self.session.get(f"{self.BASE_URL}/logout", timeout=10)
            except Exception:
                pass  # Ignore errors during logout

        self.auth_manager.clear_session()
        self.session.cookies.clear()
        logger.info("Logged out successfully")

    def search_products(self, query: str) -> list[Product]:
        """
        Search for products by name.

        Args:
            query: Product name or search term

        Returns:
            List of matching products
        """
        logger.info(f"=== SEARCH (curl_cffi): query='{query}' ===")

        try:
            self._update_cookies()

            search_response = self.session.get(
                f"{self.BASE_URL}/search",
                params={"keyphrase": query},
                timeout=30
            )
            search_response.raise_for_status()

            products = self._parse_products_from_html(search_response.text)
            logger.info(f"Found {len(products)} products")

            return products

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return []

    def get_product_details_for_cart(self, sku_id_or_url: str) -> dict:
        """
        Get product details needed for adding to cart.

        Args:
            sku_id_or_url: The SKU ID or full product URL from search

        Returns:
            Dict with product_id, shop_id, and price
        """
        logger.info(f"=== GET PRODUCT DETAILS: input={sku_id_or_url} ===")

        try:
            self._update_cookies()

            # Quick extraction from URL parameters if available
            if 'product_id=' in sku_id_or_url:
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(sku_id_or_url)
                params = urlparse.parse_qs(parsed.query)

                # Extract SKU ID from URL path
                sku_match = re.search(r'/s/(\d+)/', sku_id_or_url)
                sku_id = sku_match.group(1) if sku_match else ''

                if 'product_id' in params:
                    product_id = params['product_id'][0]
                    logger.info(f"✅ Extracted from URL - sku_id: {sku_id}, product_id: {product_id}")

                    # Return with extracted data - shop_id and price as placeholders
                    # The cart API might work with just product_id
                    return {
                        'sku_id': sku_id,
                        'product_id': product_id,
                        'shop_id': 0,  # API might not require this
                        'price': 0.0,  # API might not require this
                    }

            # Fallback: Fetch the page and try to extract from HTML
            # Determine if we have a full URL or just SKU ID
            if sku_id_or_url.startswith('http'):
                url = sku_id_or_url
                # Remove query parameters for cleaner URL
                url = url.split('?')[0] if '?' in url else url
                logger.info(f"Using full URL: {url}")
            else:
                # Try to construct URL (though this might not work without slug)
                url = f"{self.BASE_URL}/s/{sku_id_or_url}"
                logger.info(f"Constructed URL from SKU: {url}")

            response = self.session.get(url, timeout=30)
            logger.info(f"Response status: {response.status_code}")
            response.raise_for_status()

            # Save HTML for debugging FIRST
            html = response.text
            try:
                with open('/tmp/skroutz_product_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info("✓ Saved product page HTML to /tmp/skroutz_product_page.html")
            except Exception as e:
                logger.warning(f"Could not save HTML: {e}")

            # Extract product details from HTML/JSON

            # Try to find the first available offer
            import json as json_module

            # Look for JSON data in the page - multiple possible patterns
            json_patterns = [
                (r'window\.REDUX_INITIAL_STATE\s*=\s*({.*?});', False),
                (r'window\.__INITIAL_STATE__\s*=\s*({.*?});', False),
                (r'var\s+initialState\s*=\s*({.*?});', False),
                # Try non-greedy and greedy versions
                (r'window\.REDUX_INITIAL_STATE\s*=\s*(\{.+?\}\s*);', False),
                (r'<script[^>]*>\s*window\.__NEXT_DATA__\s*=\s*(\{.+?\})\s*</script>', False),
            ]

            # Special case: Skroutz uses Hypernova with base64-encoded JSON
            hypernova_match = re.search(
                r'<script[^>]*data-hypernova-key="SkuPage"[^>]*><!--([^<]+)--></script>',
                html
            )
            if hypernova_match:
                try:
                    import base64
                    encoded_data = hypernova_match.group(1)
                    decoded_data = base64.b64decode(encoded_data).decode('utf-8')
                    data = json_module.loads(decoded_data)
                    logger.info("✓ Found Hypernova JSON data")

                    # Extract SKU ID from URL
                    sku_match = re.search(r'/s/(\d+)/', url)
                    sku_id = sku_match.group(1) if sku_match else sku_id_or_url

                    # The offerings are in data['offerings']
                    if 'offerings' in data and isinstance(data['offerings'], list) and len(data['offerings']) > 0:
                        first_offer = data['offerings'][0]
                        product_id = str(first_offer.get('product_id', ''))
                        shop_id = int(first_offer.get('shop_id', 0))
                        price = float(first_offer.get('price', 0.0))

                        if product_id:
                            logger.info(f"✅ Extracted from Hypernova: sku_id={sku_id}, product_id={product_id}, shop_id={shop_id}, price={price}")
                            return {
                                'sku_id': str(sku_id),
                                'product_id': product_id,
                                'shop_id': shop_id,
                                'price': price
                            }
                except Exception as e:
                    logger.debug(f"Failed to parse Hypernova data: {e}")

            for pattern, multiline in json_patterns:
                flags = re.DOTALL if multiline else 0
                match = re.search(pattern, html, flags)
                if match:
                    try:
                        json_str = match.group(1)
                        # Handle potential issues with the JSON string
                        json_str = json_str.strip()
                        if json_str.endswith(';'):
                            json_str = json_str[:-1]

                        data = json_module.loads(json_str)
                        logger.info(f"✓ Found JSON data with pattern: {pattern[:50]}...")

                        # Extract SKU ID from URL if available
                        sku_match = re.search(r'/s/(\d+)/', url)
                        sku_id = sku_match.group(1) if sku_match else sku_id_or_url

                        # Try different data structure paths
                        offers = None
                        product_data = None

                        # Path 1: Direct offers array
                        if 'offers' in data and isinstance(data['offers'], list):
                            offers = data['offers']

                        # Path 2: Nested in product
                        elif 'product' in data:
                            product_data = data['product']
                            if isinstance(product_data, dict) and 'offers' in product_data:
                                offers = product_data['offers']

                        # Path 3: Nested in sku
                        elif 'sku' in data:
                            sku_data = data['sku']
                            if isinstance(sku_data, dict) and 'offers' in sku_data:
                                offers = sku_data['offers']

                        # Path 4: Redux-style nested structure
                        elif 'sku' in data and 'details' in data['sku']:
                            details = data['sku']['details']
                            if isinstance(details, dict) and 'offers' in details:
                                offers = details['offers']

                        # Path 5: Look for props.pageProps in Next.js apps
                        elif 'props' in data and 'pageProps' in data['props']:
                            page_props = data['props']['pageProps']
                            if 'sku' in page_props and 'offers' in page_props['sku']:
                                offers = page_props['sku']['offers']

                        if offers and isinstance(offers, list) and len(offers) > 0:
                            first_offer = offers[0]
                            logger.info(f"✓ Found first offer from {len(offers)} total offers")

                            # Extract product_id (try multiple keys)
                            product_id = (
                                first_offer.get('id') or
                                first_offer.get('product_id') or
                                first_offer.get('productId') or
                                first_offer.get('offer_id') or
                                ''
                            )

                            # Extract shop_id
                            shop_id = (
                                first_offer.get('shop_id') or
                                first_offer.get('shopId') or
                                first_offer.get('merchant_id') or
                                0
                            )

                            # Extract price
                            price = (
                                first_offer.get('price') or
                                first_offer.get('final_price') or
                                first_offer.get('finalPrice') or
                                first_offer.get('amount') or
                                0.0
                            )

                            if product_id:
                                logger.info(f"✅ Extracted: sku_id={sku_id}, product_id={product_id}, shop_id={shop_id}, price={price}")
                                return {
                                    'sku_id': str(sku_id),
                                    'product_id': str(product_id),
                                    'shop_id': int(shop_id),
                                    'price': float(price)
                                }
                    except Exception as e:
                        logger.debug(f"Failed to parse JSON with pattern {pattern[:50]}: {e}")
                        continue

            # Fallback: Try to extract from HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            logger.info("Falling back to HTML parsing...")

            # Extract SKU ID from URL
            sku_match = re.search(r'/s/(\d+)/', url)
            sku_id = sku_match.group(1) if sku_match else sku_id_or_url

            # Try multiple selectors for product offers
            offer_selectors = [
                {'attrs': {'data-product-id': True}},
                {'attrs': {'data-productid': True}},
                {'attrs': {'data-product': True}},
                {'attrs': {'data-offer-id': True}},
                {'attrs': {'data-shop-id': True}},
                {'class': re.compile(r'product-offer', re.I)},
                {'class': re.compile(r'offer-item', re.I)},
                {'class': re.compile(r'sku-offer', re.I)},
            ]

            for selector in offer_selectors:
                offer_elem = soup.find(['div', 'li', 'article', 'a', 'button'], **selector)
                if offer_elem:
                    logger.info(f"Found potential offer element with selector: {selector}")

                    # Try all possible data attribute names
                    product_id = (
                        offer_elem.get('data-product-id') or
                        offer_elem.get('data-productid') or
                        offer_elem.get('data-product') or
                        offer_elem.get('data-offer-id') or
                        offer_elem.get('data-offerid')
                    )

                    shop_id = (
                        offer_elem.get('data-shop-id') or
                        offer_elem.get('data-shopid') or
                        offer_elem.get('data-merchant-id') or
                        offer_elem.get('data-merchantid') or
                        '0'
                    )

                    # Try to find price - multiple strategies
                    price = 0.0

                    # Strategy 1: data attributes
                    price_from_data = (
                        offer_elem.get('data-price') or
                        offer_elem.get('data-final-price') or
                        offer_elem.get('data-amount')
                    )
                    if price_from_data:
                        try:
                            price = float(str(price_from_data).replace(',', '.'))
                        except:
                            pass

                    # Strategy 2: find price element
                    if price == 0.0:
                        price_elem = offer_elem.find(['span', 'div', 'a', 'strong'],
                                                    class_=re.compile(r'price', re.I))
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            price_match = re.search(r'([\d.,]+)\s*€', price_text)
                            if price_match:
                                price_str = price_match.group(1).replace('.', '').replace(',', '.')
                                try:
                                    price = float(price_str)
                                except:
                                    pass

                    # Strategy 3: search in all text content
                    if price == 0.0:
                        all_text = offer_elem.get_text()
                        price_match = re.search(r'([\d.,]+)\s*€', all_text)
                        if price_match:
                            price_str = price_match.group(1).replace('.', '').replace(',', '.')
                            try:
                                price = float(price_str)
                            except:
                                pass

                    if product_id:
                        logger.info(f"✓ Found product via HTML: product_id={product_id}, shop_id={shop_id}, price={price}")
                        return {
                            'sku_id': str(sku_id),
                            'product_id': str(product_id),
                            'shop_id': int(shop_id) if shop_id and str(shop_id).isdigit() else 0,
                            'price': float(price)
                        }

            # Save HTML for debugging
            try:
                with open('/tmp/skroutz_product_page.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info("Saved product page HTML to /tmp/skroutz_product_page.html for debugging")
            except:
                pass

            logger.error("Could not extract product details from page")
            return {}

        except Exception as e:
            logger.error(f"Get product details error: {e}", exc_info=True)
            return {}

    def add_to_cart(self, sku_id: str, product_id: str, shop_id: int, price: float, quantity: int = 1) -> bool:
        """
        Add a product to the shopping cart.

        Args:
            sku_id: SKU ID (product identifier)
            product_id: Specific product/offer ID
            shop_id: Shop/merchant ID
            price: Product price
            quantity: Quantity to add (default: 1)

        Returns:
            True if successful
        """
        logger.info(f"=== ADD TO CART (curl_cffi): sku={sku_id}, product={product_id}, shop={shop_id} ===")

        if not self.auth_manager.is_authenticated():
            logger.error("ADD TO CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            # Get CSRF token
            csrf_token = self._get_current_csrf_token()

            # Prepare request body based on HAR analysis
            body = {
                "product_id": int(product_id),
                "assortments": {},
                "from": "sku",
                "offering_type": "default",
                "express": None,
                "recommendation_source_sku_id": None,
                "offerings": [
                    {
                        "shop_id": int(shop_id),
                        "type": "default",
                        "price": float(price),
                        "pro": False,
                        "order": 0,
                        "expanded": True,
                    }
                ]
            }

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf_token,
                "Referer": f"{self.BASE_URL}/s/{sku_id}",
            }

            response = self.session.post(
                f"{self.BASE_URL}/cart/add/{sku_id}.json",
                json=body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                self._save_cookies()
                logger.info("ADD TO CART SUCCESS")
                try:
                    result = response.json()
                    logger.info(f"Cart items count: {result.get('cart_items_count', 'unknown')}")
                    return True
                except:
                    return True

            logger.error(f"ADD TO CART FAILED: status={response.status_code}")
            logger.error(f"Response: {response.text[:200]}")
            return False

        except Exception as e:
            logger.error(f"Add to cart error: {e}", exc_info=True)
            return False

    def remove_from_cart(self, line_item_id: str) -> bool:
        """
        Remove a product from the shopping cart.

        Args:
            line_item_id: Line item ID from cart (not product_id)

        Returns:
            True if successful
        """
        logger.info(f"=== REMOVE FROM CART (curl_cffi): line_item_id={line_item_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            # Use the correct Skroutz endpoint
            response = self.session.post(
                f"{self.BASE_URL}/cart/remove_line_item/{line_item_id}",
                timeout=30,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                }
            )

            if response.status_code in [200, 204, 302]:
                self._save_cookies()
                logger.info("REMOVE FROM CART SUCCESS")
                return True

            logger.error(f"REMOVE FROM CART FAILED: status={response.status_code}")
            logger.error(f"Response: {response.text[:200]}")
            return False

        except Exception as e:
            logger.error(f"Remove from cart error: {e}", exc_info=True)
            return False

    def _get_current_csrf_token(self) -> Optional[str]:
        """Get current CSRF token from the site."""
        try:
            response = self.session.get(f"{self.BASE_URL}/cart", timeout=10)
            if response.status_code == 200:
                csrf_token = self._extract_csrf_token(response.text)
                return csrf_token
        except Exception as e:
            logger.warning(f"Failed to get CSRF token: {e}")
        return None

    def update_cart_item_quantity(self, line_item_id: str, quantity: int) -> bool:
        """
        Update the quantity of a product in the shopping cart.

        Args:
            line_item_id: Line item ID (from cart JSON response)
            quantity: New quantity to set

        Returns:
            True if successful
        """
        logger.info(f"=== UPDATE CART (curl_cffi): line_item_id={line_item_id}, new_quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        self._update_cookies()

        try:
            csrf_token = self._get_current_csrf_token()

            body = {
                "line_item_id": int(line_item_id),
                "quantity": int(quantity),
                "from_sku_page": False
            }

            headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf_token,
                "Referer": f"{self.BASE_URL}/cart",
            }

            response = self.session.post(
                f"{self.BASE_URL}/cart/change_line_item_quantity.json",
                json=body,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                self._save_cookies()
                logger.info("UPDATE CART SUCCESS")
                try:
                    result = response.json()
                    logger.info(f"New cart count: {result.get('cart_items_count', 'unknown')}")
                    return True
                except:
                    return True

            logger.error(f"UPDATE CART FAILED: status={response.status_code}")
            logger.error(f"Response: {response.text[:200]}")
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
        logger.info("=== GET CART (curl_cffi) ===")

        if not self.auth_manager.is_authenticated():
            logger.error("GET CART FAILED: Not authenticated")
            raise Exception("Must be authenticated to view cart")

        self._update_cookies()

        try:
            # Strategy 1: Try JSON API endpoint (most reliable, has all data including prices)
            logger.info("Attempting to fetch cart via JSON API")
            json_headers = {
                "Accept": "application/json",
                "Referer": f"{self.BASE_URL}/cart",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            try:
                json_response = self.session.get(
                    f"{self.BASE_URL}/cart.json",
                    timeout=30,
                    headers=json_headers
                )

                if json_response.status_code == 200:
                    logger.info("✓ Got cart via /cart.json API")
                    import json as json_module
                    cart_data = json_module.loads(json_response.text)
                    cart = self._parse_cart_from_json(cart_data)
                    logger.info(f"✓ Cart parsed from JSON: item_count={cart.item_count}, items={len(cart.items)}, total={cart.total}€")

                    # If we got items, return immediately
                    if cart.items or cart.item_count > 0:
                        return cart
            except Exception as json_e:
                logger.warning(f"JSON API /cart.json failed: {json_e}")

            # Strategy 2: Visit main cart page first to establish session, then mini_cart
            logger.info("Visiting main cart page to establish session")
            visit_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "el-GR,el;q=0.9",
                "Referer": f"{self.BASE_URL}/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }

            visit_response = self.session.get(
                f"{self.BASE_URL}/cart",
                timeout=30,
                headers=visit_headers
            )

            logger.info(f"Initial cart visit: status={visit_response.status_code}")

            # Small delay to appear human
            import time
            time.sleep(0.5)

            # Now try mini_cart as AJAX request (should have the items with HTML)
            logger.info("Fetching mini_cart as AJAX")
            mini_cart_headers = {
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}/cart",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            mini_response = self.session.get(
                f"{self.BASE_URL}/cart/mini_cart",
                timeout=30,
                headers=mini_cart_headers
            )

            logger.info(f"mini_cart response: status={mini_response.status_code}, length={len(mini_response.text)}")

            if mini_response.status_code == 200:
                # Check if it's not blocked
                if 'cloudflare' in mini_response.text.lower() and 'challenge' in mini_response.text.lower():
                    logger.warning("mini_cart blocked by Cloudflare")
                else:
                    logger.info("✓ Got mini_cart data")
                    cart = self._parse_cart_from_html(mini_response.text)
                    logger.info(f"✓ Cart parsed from mini_cart: item_count={cart.item_count}, total={cart.total}")

                    # If we got items, return them
                    if cart.items or cart.item_count > 0:
                        return cart

            # Strategy 3: Direct full cart attempt
            logger.info(f"Fetching cart from {self.BASE_URL}/cart")
            response = self.session.get(f"{self.BASE_URL}/cart", timeout=30)
            logger.info(f"Cart response: status={response.status_code}, content_length={len(response.text)}")

            # Check for Cloudflare before raising for status
            if response.status_code == 403:
                if 'cloudflare' in response.text.lower():
                    logger.error("⚠️  403 Forbidden - Cloudflare is blocking the request")
                    raise Exception("Cloudflare blocked the cart request (403 Forbidden)")
                else:
                    logger.error("⚠️  403 Forbidden - Access denied (not Cloudflare)")
                    raise Exception("Access denied to cart (403 Forbidden)")

            response.raise_for_status()

            cart = self._parse_cart_from_html(response.text)
            logger.info(f"✓ Cart parsed: item_count={cart.item_count}, total={cart.total}")

            return cart

        except Exception as e:
            logger.error(f"Get cart error: {e}", exc_info=True)
            # Re-raise if it's a Cloudflare error so the user knows
            if "cloudflare" in str(e).lower():
                raise
            return Cart()

    def get_orders(self, include_history: bool = True) -> list[Order]:
        """
        Get user's orders.

        Args:
            include_history: If True, include past orders; if False, only current orders

        Returns:
            List of orders
        """
        logger.info("=== GET ORDERS (curl_cffi) ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        try:
            # Strategy 1: Try JSON API first (less likely to be blocked by Cloudflare)
            logger.info("Attempting to fetch orders via JSON API")
            json_headers = {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}/account/orders",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            # Try possible JSON endpoints
            json_endpoints = [
                "/account/orders.json",
                "/api/orders",
                "/ecommerce/api/v1/orders",
            ]

            for endpoint in json_endpoints:
                try:
                    json_response = self.session.get(
                        f"{self.BASE_URL}{endpoint}",
                        timeout=30,
                        headers=json_headers
                    )

                    if json_response.status_code == 200:
                        logger.info(f"✓ Got orders via JSON from {endpoint}")
                        import json as json_module
                        orders_data = json_module.loads(json_response.text)
                        orders = self._parse_orders_from_json(orders_data)
                        logger.info(f"✓ Parsed {len(orders)} orders from JSON")

                        if not include_history:
                            orders = [
                                o for o in orders
                                if o.status.lower() in ["pending", "confirmed", "processing"]
                            ]

                        return orders
                except Exception as json_e:
                    logger.debug(f"JSON endpoint {endpoint} failed: {json_e}")

            # Strategy 2: Try HTML page with AJAX headers (bypasses Cloudflare for orders)
            logger.info("Fetching orders from HTML page with AJAX headers")
            ajax_headers = {
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}/account",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            response = self.session.get(
                f"{self.BASE_URL}/account/orders",
                timeout=30,
                headers=ajax_headers
            )
            logger.info(f"Orders page response: status={response.status_code}")

            if response.status_code != 200:
                logger.error(f"Failed to fetch orders: status={response.status_code}")
                return []

            # Check for Cloudflare
            if 'checking your browser' in response.text.lower() or 'challenge-running' in response.text.lower():
                logger.error("⚠️ Cloudflare blocked orders page")
                raise Exception("Cloudflare blocked the orders request. Try again in a few moments or the data may require browser-based access.")

            # Save for debugging
            try:
                with open('/tmp/skroutz_orders.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                logger.info("Saved orders HTML to /tmp/skroutz_orders.html")
            except:
                pass

            orders = self._parse_orders_from_html(response.text)
            logger.info(f"Found {len(orders)} orders from HTML")

            if not include_history:
                orders = [
                    o
                    for o in orders
                    if o.status.lower() in ["pending", "confirmed", "processing"]
                ]

            return orders

        except Exception as e:
            logger.error(f"Get orders error: {e}", exc_info=True)
            # Re-raise Cloudflare errors
            if "cloudflare" in str(e).lower():
                raise
            return []

    def get_order_details(self, order_id: str) -> Optional[Order]:
        """
        Get detailed information for a specific order, including items.

        Args:
            order_id: Order ID to fetch details for

        Returns:
            Order object with items, or None if order not found
        """
        logger.info(f"=== GET ORDER DETAILS (curl_cffi): order_id={order_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        self._update_cookies()

        try:
            # Use AJAX headers to bypass Cloudflare
            ajax_headers = {
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.BASE_URL}/account/orders",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            response = self.session.get(
                f"{self.BASE_URL}/account/ecommerce/orders/{order_id}",
                timeout=30,
                headers=ajax_headers
            )

            logger.info(f"Order details response: status={response.status_code}")

            if response.status_code == 404:
                logger.error(f"Order {order_id} not found (404)")
                return None

            # Check for Cloudflare
            if 'checking your browser' in response.text.lower() or 'challenge-running' in response.text.lower():
                logger.error("⚠️ Cloudflare blocked order details")
                raise Exception(f"Cloudflare blocked the order details request for {order_id}")

            response.raise_for_status()

            order = self._parse_order_details_from_html(response.text, order_id)
            logger.info(f"Order details retrieved for {order_id}")

            return order

        except Exception as e:
            logger.error(f"Get order details error: {e}", exc_info=True)
            if "cloudflare" in str(e).lower():
                raise
            return None

    # Helper methods for parsing responses (reused from original client)

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
        """Parse products from HTML response, excluding sponsored/promoted items."""
        from bs4 import BeautifulSoup

        products = []
        soup = BeautifulSoup(html, 'lxml')

        # Skroutz uses li elements with data-skuid attribute
        product_elements = soup.find_all('li', attrs={'data-skuid': True})

        if not product_elements:
            # Fallback to old parsing
            product_elements = soup.find_all(['li', 'div'], class_=re.compile(r'product|item', re.I))

        for elem in product_elements[:50]:
            # Filter out sponsored/promoted products based on uBlock filters
            classes = elem.get('class', [])
            if isinstance(classes, str):
                classes = [classes]

            # Skip labeled/sponsored products
            if any(cls in classes for cls in ['labeled-product', 'labeled-item', 'product-ad']):
                continue

            # Skip if parent is a selected-product-cards or sponsored container
            parent = elem.parent
            if parent:
                parent_classes = parent.get('class', [])
                if isinstance(parent_classes, str):
                    parent_classes = [parent_classes]
                if any(cls in parent_classes for cls in ['selected-product-cards', 'product-ad']):
                    continue

            # Skip if element has data-ad or sponsored attributes
            if elem.get('data-ad') or elem.get('data-sponsored'):
                continue
            try:
                # Get SKU ID from data attribute
                sku_id = elem.get('data-skuid', '')

                # Find product link (usually has /s/{sku_id}/ in href)
                link_elem = elem.find('a', href=re.compile(r'/s/\d+/'))

                if not link_elem:
                    continue

                # Get product name from link text or title
                name = link_elem.get('title') or link_elem.get_text(strip=True)

                # Get href for full URL
                href = link_elem.get('href', '')

                # Extract SKU ID from URL if not in data attribute
                if not sku_id:
                    id_match = re.search(r'/s/(\d+)/', href)
                    if id_match:
                        sku_id = id_match.group(1)

                # Find price - multiple strategies
                price = Decimal("0")
                # Strategy 1: Look for elements with price-related classes
                price_elem = elem.find(['span', 'div', 'strong'], class_=re.compile(r'price', re.I))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'([\d.,]+)\s*€', price_text)
                    if price_match:
                        price_str = price_match.group(1).replace('.', '').replace(',', '.')
                        try:
                            price = Decimal(price_str)
                        except:
                            pass

                # Strategy 2: If no price found, search in all text for € pattern
                if price == Decimal("0"):
                    all_text = elem.get_text()
                    price_matches = re.findall(r'([\d.,]+)\s*€', all_text)
                    if price_matches:
                        # Get the first reasonable price (usually the main price)
                        for match in price_matches:
                            try:
                                price_str = match.replace('.', '').replace(',', '.')
                                test_price = Decimal(price_str)
                                if test_price > 0:
                                    price = test_price
                                    break
                            except:
                                continue

                # Check availability
                available = True
                # Look for out of stock indicators
                availability_text = elem.get_text().lower()
                if any(phrase in availability_text for phrase in ['εξαντλημένο', 'out of stock', 'μη διαθέσιμο']):
                    available = False

                # Find image
                image_elem = elem.find('img')
                image_url = None
                if image_elem:
                    image_url = image_elem.get('src') or image_elem.get('data-src')

                # Build full URL - remove query parameters that can cause issues
                full_url = None
                if href:
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{self.BASE_URL}{href}"

                    # Clean up URL - remove problematic query parameters but keep structure
                    if full_url and '?' in full_url:
                        # Only keep the base URL without query params for reliability
                        full_url = full_url.split('?')[0]

                if name and sku_id:
                    product = Product(
                        id=sku_id,
                        sku_id=sku_id,
                        name=name,
                        price=price,
                        available=available,
                        image_url=image_url,
                        url=full_url,
                    )
                    products.append(product)

            except Exception as e:
                logger.warning(f"Failed to parse product: {e}")
                continue

        return products

    def _parse_cart_from_json(self, cart_data: dict) -> Cart:
        """Parse cart from JSON response (Skroutz format with proposals/suborders)."""
        items = []
        total = Decimal("0")

        # Skroutz cart.json structure: cart.proposals[].suborders[].items[]
        if 'cart' in cart_data:
            cart_obj = cart_data['cart']

            # Get total from summary
            if 'proposals' in cart_obj and len(cart_obj['proposals']) > 0:
                first_proposal = cart_obj['proposals'][0]

                # Extract total cost
                if 'summary' in first_proposal:
                    summary = first_proposal['summary']
                    total_str = summary.get('total_cost', '0 €')
                    # Parse "335,55 €" format
                    total_match = re.search(r'([\d.,]+)', total_str)
                    if total_match:
                        total_clean = total_match.group(1).replace('.', '').replace(',', '.')
                        try:
                            total = Decimal(total_clean)
                            logger.info(f"Parsed total from summary: {total}")
                        except:
                            pass

                # Extract items from packages (Skroutz uses packages, not suborders)
                if 'packages' in first_proposal:
                    for package in first_proposal['packages']:
                        if 'items' in package:
                            for item_data in package['items']:
                                try:
                                    # Extract item details
                                    line_item_id = str(item_data.get('id', ''))
                                    sku_id = str(item_data.get('sku_id', ''))
                                    product_name = item_data.get('name', 'Unknown')
                                    manufacturer = item_data.get('manufacturer', '')
                                    quantity = int(item_data.get('quantity', 1))

                                    # Parse total_cost "136,25 €"
                                    total_cost_str = item_data.get('total_cost', '0 €')
                                    total_cost_match = re.search(r'([\d.,]+)', total_cost_str)
                                    subtotal = Decimal("0")
                                    if total_cost_match:
                                        subtotal_clean = total_cost_match.group(1).replace('.', '').replace(',', '.')
                                        try:
                                            subtotal = Decimal(subtotal_clean)
                                        except:
                                            pass

                                    # Calculate unit price
                                    price = subtotal / quantity if quantity > 0 else Decimal("0")

                                    product = Product(
                                        id=line_item_id,
                                        sku_id=sku_id,
                                        name=product_name,
                                        maker=manufacturer,
                                        price=price,
                                        available=True,
                                        url=item_data.get('link'),
                                        image_url=item_data.get('sku_image'),
                                    )

                                    cart_item = CartItem(
                                        product=product,
                                        quantity=quantity,
                                        subtotal=subtotal,
                                    )
                                    items.append(cart_item)
                                    logger.info(f"Parsed item: {product_name} x{quantity} = {subtotal}€")

                                except Exception as e:
                                    logger.warning(f"Failed to parse cart item from JSON: {e}")
                                    continue

        return Cart(
            items=items,
            total=total,
            item_count=sum(item.quantity for item in items),
        )

    def _parse_cart_from_html(self, html: str) -> Cart:
        """Parse cart from HTML response."""
        from bs4 import BeautifulSoup

        # Save for debugging
        try:
            with open('/tmp/skroutz_cart.html', 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info("Saved cart HTML to /tmp/skroutz_cart.html")
        except Exception as e:
            logger.warning(f"Could not save cart HTML: {e}")

        # Check for Cloudflare challenge (but not just the beacon)
        if ('checking your browser' in html.lower() or
            'challenge-running' in html.lower() or
            ('cloudflare' in html.lower() and '<title>Just a moment' in html)):
            logger.error("⚠️  CLOUDFLARE CHALLENGE DETECTED - Cart page is blocked")
            # Try to extract title for better error message
            title_match = re.search(r'<title>([^<]+)</title>', html, re.I)
            if title_match:
                logger.error(f"   Page title: {title_match.group(1)}")
            raise Exception("Cloudflare challenge detected. The request was blocked by Cloudflare protection.")

        soup = BeautifulSoup(html, 'lxml')
        items = []
        total = Decimal("0")

        # Check if this is a React-based cart page (empty div#react-cart-page)
        react_cart_div = soup.find('div', id='react-cart-page')
        if react_cart_div and not react_cart_div.get_text(strip=True):
            logger.info("Detected React-based cart page - data will be in JavaScript")

            # Try to extract cart count from JavaScript
            cart_count_match = re.search(r'cart_items_count\s*=\s*(\d+)', html)
            if cart_count_match:
                cart_count = int(cart_count_match.group(1))
                logger.info(f"Found cart_items_count in JS: {cart_count}")

                # For React carts, we need to rely on AJAX endpoints
                # Return a cart with count but no items (will be filled by JSON API if available)
                if cart_count > 0:
                    logger.warning(f"React cart detected with {cart_count} items, but cannot parse without JSON API")
                    # Return minimal cart info
                    return Cart(
                        items=[],
                        total=Decimal("0"),
                        item_count=cart_count,
                    )

        # Extract cart count from title
        cart_title = soup.find('strong', class_=re.compile(r'cart-quantity', re.I))
        if cart_title:
            title_text = cart_title.get_text(strip=True)
            logger.info(f"Cart title: {title_text}")

        # Try multiple selectors for cart items
        cart_items = soup.find_all('li')  # Mini-cart uses simple li elements
        if not cart_items:
            cart_items = soup.find_all(['div', 'tr'], class_=re.compile(r'cart.*item|line.*item', re.I))

        logger.info(f"Found {len(cart_items)} potential cart items")

        for idx, item_elem in enumerate(cart_items):
            try:
                logger.debug(f"Processing cart item {idx}")

                # Look for suborder-item-details link (Skroutz mini-cart format)
                link_elem = item_elem.find('a', class_='suborder-item-details')
                if not link_elem:
                    # Fallback to any product link
                    link_elem = item_elem.find('a', href=re.compile(r'/s/\d+/'))
                if not link_elem:
                    logger.debug(f"  No link found in item {idx}")
                    continue

                # Get product name from link text
                name = link_elem.get_text(strip=True)
                if not name or len(name) < 3:
                    # Try getting from title attribute
                    name = link_elem.get('title', '')
                if not name or len(name) < 3:
                    continue

                # Find quantity - look for <p class="quantity"><strong>X</strong></p>
                quantity = 1
                qty_paragraph = item_elem.find('p', class_='quantity')
                if qty_paragraph:
                    qty_strong = qty_paragraph.find('strong')
                    if qty_strong:
                        try:
                            quantity = int(qty_strong.get_text(strip=True))
                        except:
                            pass

                # Find price (might not be in mini-cart)
                price = Decimal("0")
                price_elem = item_elem.find(['span', 'div', 'strong'], class_=re.compile(r'price', re.I))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'([\d.,]+)\s*€', price_text)
                    if price_match:
                        price_str = price_match.group(1).replace('.', '').replace(',', '.')
                        try:
                            price = Decimal(price_str)
                        except:
                            pass

                # Extract line_item_id from remove link for later operations
                remove_link = item_elem.find('a', class_='remove')
                line_item_id = ''
                if remove_link:
                    remove_href = remove_link.get('href', '')
                    id_match = re.search(r'/remove_line_item/(\d+)', remove_href)
                    if id_match:
                        line_item_id = id_match.group(1)

                product = Product(
                    id=line_item_id or f"cart_item_{len(items)}",
                    name=name,
                    price=price,
                    available=True,
                )

                cart_item = CartItem(
                    product=product,
                    quantity=quantity,
                    subtotal=price * quantity if price > 0 else Decimal("0"),
                )
                items.append(cart_item)
                logger.info(f"  ✓ Parsed: {name} x{quantity}")

            except Exception as e:
                logger.warning(f"Failed to parse cart item {idx}: {e}", exc_info=True)
                continue

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

    def _parse_orders_from_json(self, orders_data: dict) -> list[Order]:
        """Parse orders from JSON response."""
        orders = []

        # Try to find orders in different possible structures
        orders_list = []
        if isinstance(orders_data, list):
            orders_list = orders_data
        elif 'orders' in orders_data:
            orders_list = orders_data['orders']
        elif 'data' in orders_data:
            orders_list = orders_data['data']

        for order_data in orders_list:
            try:
                order = Order(
                    id=str(order_data.get('id', order_data.get('order_id', ''))),
                    order_number=str(order_data.get('code', order_data.get('order_number', ''))),
                    status=order_data.get('status', 'unknown'),
                    created_at=datetime.fromisoformat(order_data.get('created_at', datetime.now().isoformat())),
                    total=Decimal(str(order_data.get('total', order_data.get('amount', 0)))),
                )
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to parse order from JSON: {e}")
                continue

        return orders

    def _parse_orders_from_html(self, html: str) -> list[Order]:
        """Parse orders from HTML response."""
        from bs4 import BeautifulSoup

        orders = []
        soup = BeautifulSoup(html, 'lxml')

        # Skroutz uses order-code class for order numbers
        order_code_elements = soup.find_all('span', class_='order-code')
        logger.info(f"Found {len(order_code_elements)} order-code elements")

        for code_elem in order_code_elements:
            try:
                order_number = code_elem.get_text(strip=True)

                # Extract order ID (remove prefix like "25" from "250921-2298786")
                order_id_match = re.search(r'\d+-(\d+)', order_number)
                order_id = order_id_match.group(1) if order_id_match else order_number

                # Find parent container for this order
                order_container = code_elem.find_parent(['div', 'article', 'section'])

                status = "unknown"
                created_at = datetime.now()
                total = Decimal("0")

                if order_container:
                    # Find status
                    status_elem = order_container.find(['span', 'div', 'p'], class_=re.compile(r'status|state', re.I))
                    if status_elem:
                        status = status_elem.get_text(strip=True)

                    # Find date - look for datetime patterns
                    date_elem = order_container.find(['span', 'time', 'p'], class_=re.compile(r'date|time|created', re.I))
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        # Try multiple date formats
                        for fmt in ['%d/%m/%Y %I:%M %p', '%d/%m/%Y', '%Y-%m-%d']:
                            try:
                                # Clean Greek am/pm indicators
                                date_text_clean = date_text.replace(' μ.μ.', ' PM').replace(' π.μ.', ' AM')
                                created_at = datetime.strptime(date_text_clean, fmt)
                                break
                            except:
                                continue

                    # Find total cost
                    total_elem = order_container.find(['span', 'div', 'strong'], class_=re.compile(r'total|cost|price', re.I))
                    if not total_elem:
                        # Look for € symbol in text
                        all_text = order_container.get_text()
                        total_matches = re.findall(r'([\d.,]+)\s*€', all_text)
                        if total_matches:
                            # Get the largest amount (usually the total)
                            for match in total_matches:
                                try:
                                    price_str = match.replace('.', '').replace(',', '.')
                                    test_total = Decimal(price_str)
                                    if test_total > total:
                                        total = test_total
                                except:
                                    continue

                if order_number:
                    order = Order(
                        id=order_id,
                        order_number=order_number,
                        status=status,
                        created_at=created_at,
                        total=total,
                    )
                    orders.append(order)
                    logger.debug(f"Parsed order: {order_number}, status={status}, total={total}")

            except Exception as e:
                logger.warning(f"Failed to parse order: {e}")
                continue

        logger.info(f"Successfully parsed {len(orders)} orders")
        return orders

    def _parse_order_details_from_html(self, html: str, order_id: str) -> Optional[Order]:
        """Parse order details from HTML response."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        items = []

        # Skroutz uses class="suborder-item" for order items
        item_elements = soup.find_all('div', class_='suborder-item')
        logger.info(f"Found {len(item_elements)} suborder-item elements")

        for item_elem in item_elements:
            try:
                # Find product name from link
                name_elem = item_elem.find('a', href=re.compile(r'/s/\d+/'))
                if not name_elem:
                    logger.debug("No product link found in item")
                    continue

                product_name = name_elem.get_text(strip=True)

                # Find quantity and price from suborder-item-numeric
                numeric_elem = item_elem.find('p', class_='suborder-item-numeric')
                quantity = 1
                price = Decimal("0")
                subtotal = Decimal("0")

                if numeric_elem:
                    # Structure: <span>2</span> <i>×</i> <span>8,53 €</span>
                    spans = numeric_elem.find_all('span')
                    if len(spans) >= 2:
                        # First span is quantity
                        try:
                            quantity = int(spans[0].get_text(strip=True))
                        except:
                            pass

                        # Second span is unit price
                        price_text = spans[1].get_text(strip=True)
                        price_match = re.search(r'([\d.,]+)', price_text)
                        if price_match:
                            price_str = price_match.group(1).replace('.', '').replace(',', '.')
                            try:
                                price = Decimal(price_str)
                                subtotal = price * quantity
                            except:
                                pass

                if product_name and len(product_name) > 3:
                    order_item = OrderItem(
                        product_name=product_name,
                        quantity=quantity,
                        price=price,
                        subtotal=subtotal,
                    )
                    items.append(order_item)
                    logger.debug(f"Parsed item: {product_name} x{quantity} @ {price}€")

            except Exception as e:
                logger.warning(f"Failed to parse order item: {e}")
                continue

        logger.info(f"Parsed {len(items)} items from order")

        order_number = order_id
        status = "unknown"
        created_at = datetime.now()
        total = Decimal("0")

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
        """Close the session."""
        self.session.close()
