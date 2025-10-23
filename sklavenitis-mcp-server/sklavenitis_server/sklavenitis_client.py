"""Sklavenitis API client with fixed add-to-cart."""

import json
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from pathlib import Path

from curl_cffi import requests
from .models import Product, Cart, CartItem
from .auth import AuthManager

logger = logging.getLogger(__name__)


class SklavenitisClient:
    """Client for Sklavenitis API."""

    BASE_URL = "https://www.sklavenitis.gr"

    def __init__(self, auth_manager: AuthManager) -> None:
        """Initialize client."""
        self.auth_manager = auth_manager
        self.session = requests.Session(impersonate="chrome120")
        self._update_cookies()

    def _update_cookies(self) -> None:
        """Load cookies from auth manager into session."""
        cookies = self.auth_manager.get_cookies()
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".sklavenitis.gr")

    def _save_cookies(self) -> None:
        """Save current session cookies to auth manager."""
        cookies = dict(self.session.cookies)
        if cookies:
            self.auth_manager.save_session(cookies)

    async def login(self, email: str, password: str) -> bool:
        """
        Login to Sklavenitis.
        
        Note: This may fail due to reCAPTCHA enforcement. If it fails,
        users should extract cookies manually from their browser.
        """
        logger.info(f"Attempting login for {email}")
        
        try:
            # Step 1: Visit homepage to establish session
            self.session.get(f"{self.BASE_URL}/")
            
            # Step 2: Get login form for CSRF token
            response = self.session.get(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/",
                headers={
                    "X-UserFlow-New": "true",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            
            # Extract CSRF token
            csrf_match = re.search(
                r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)["\']',
                response.text
            )
            
            if not csrf_match:
                logger.error("Could not extract CSRF token")
                return False
            
            csrf_token = csrf_match.group(1)
            
            # Step 3: Submit login
            login_response = self.session.post(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/",
                data={
                    "__RequestVerificationToken": csrf_token,
                    "FormName": "Login",
                    "Email": email,
                    "Password": password,
                    "RememberMe": "true",
                    "g-recaptcha-response": "",  # May fail due to reCAPTCHA
                    "returnUrl": "/",
                    "isHomePage": "true",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-NoRedirect": "true",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            
            # Check for auth cookie
            has_auth = any(".AspNet.ApplicationCookie" in name for name in self.session.cookies.keys())
            
            if has_auth:
                logger.info("✓ Login successful")
                self._save_cookies()
                return True
            else:
                logger.error("Login failed - no auth cookie received")
                logger.info("This may be due to reCAPTCHA enforcement")
                logger.info("Try extracting cookies manually from your browser")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return False

    def logout(self) -> None:
        """Logout and clear session."""
        try:
            self.session.get(f"{self.BASE_URL}/gr/account/logout")
        except:
            pass
        self.auth_manager.clear_session()

    def search_products(self, query: str) -> list[Product]:
        """Search for products."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.Autocomplete.SearchAutocomplete/",
                params={"term": query},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                products = []
                for item in data:
                    url = item.get("url", "")
                    match = re.search(r'-(\d+)/?$', url)
                    if match:
                        sku = match.group(1)
                        products.append(Product(
                            id=sku,
                            name=item.get("label", ""),
                            description=item.get("category"),
                        ))
                return products
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def add_to_cart(self, product_sku: str, quantity: int = 1) -> bool:
        """
        Add product to cart with BOTH required steps:
        1. Add the product
        2. Select delivery slot (required to finalize)
        """
        logger.info(f"Adding product {product_sku} to cart (qty: {quantity})")

        try:
            # Step 1: Add product
            response1 = self.session.post(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/",
                data={
                    "Action": "Update",
                    f"CartItems[0][ProductSKU]": product_sku,
                    f"CartItems[0][Quantity]": str(quantity),
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-UserFlow-New": "true",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

            if response1.status_code != 200:
                logger.error(f"Step 1 failed: {response1.status_code}")
                return False

            # Step 2: Select delivery slot (tomorrow 7:00-9:00)
            tomorrow = datetime.now() + timedelta(days=1)
            slot_start = tomorrow.replace(hour=7, minute=0, second=0)
            slot_end = tomorrow.replace(hour=9, minute=0, second=0)

            response2 = self.session.post(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/",
                data={
                    "TimeSlotDate": slot_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "TimeSlotDateTo": slot_end.strftime("%Y-%m-%d %H:%M:%S"),
                    "RequiresNotification": "False",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-NoRedirect": "true",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

            if response2.status_code != 200:
                logger.error(f"Step 2 failed: {response2.status_code}")
                return False

            logger.info("✓ Product added to cart successfully")
            return True

        except Exception as e:
            logger.error(f"Add to cart error: {e}", exc_info=True)
            return False

    def get_cart(self) -> Cart:
        """Get cart contents."""
        try:
            response = self.session.post(
                f"{self.BASE_URL}/gr/ajax/Atcom.Sites.Yoda.Components.ClientContext.Index/?type=Cart",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )

            if response.status_code == 200:
                data = response.json()

                # Parse items
                items_dict = {}
                for sku, details in data.get("Items", {}).items():
                    items_dict[sku] = CartItem(
                        sku=sku,
                        name=f"Product {sku}",  # Name not in cart response
                        quantity=details.get("CartQuantity", "0"),
                        price=details.get("SummaryQuantity", "0"),
                    )

                return Cart(
                    items=items_dict,
                    summary_text=data.get("SummaryText", "0"),
                    grand_total=data.get("GrandTotal", "€0"),
                    slot_info=data.get("SlotInfoWithDay"),
                )
        except Exception as e:
            logger.error(f"Get cart error: {e}")

        return Cart()

