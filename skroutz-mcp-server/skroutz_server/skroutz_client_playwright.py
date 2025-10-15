"""Skroutz.gr client using Playwright for browser automation with Cloudflare bypass."""

import logging
import re
import asyncio
import random
from decimal import Decimal
from typing import Any, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from .auth import AuthManager
from .models import AuthCredentials, Cart, CartItem, Order, OrderItem, Product

logger = logging.getLogger(__name__)

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    logger.warning("playwright-stealth not available, using built-in anti-detection only")


class SkroutzClientPlaywright:
    """Client for interacting with skroutz.gr using Playwright with anti-detection."""

    BASE_URL = "https://www.skroutz.gr"

    def __init__(self, auth_manager: AuthManager, headless: bool = True) -> None:
        """
        Initialize the Skroutz Playwright client.

        Args:
            auth_manager: Authentication manager instance
            headless: Run browser in headless mode (note: headless may trigger more Cloudflare checks)
        """
        self.auth_manager = auth_manager
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def _start_browser(self) -> None:
        """Start the Playwright browser with anti-detection settings."""
        if self.playwright is None:
            self.playwright = await async_playwright().start()

            # Launch with comprehensive anti-detection arguments
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                    '--start-maximized',
                    '--disable-extensions',
                    '--disable-hang-monitor',
                    '--disable-gpu',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--no-pings',
                    '--password-store=basic',
                    '--use-mock-keychain',
                ]
            )

            # Create context with realistic browser settings
            cookies = self.auth_manager.get_cookies()
            cookie_list = []

            if cookies:
                for name, value in cookies.items():
                    cookie_list.append({
                        "name": name,
                        "value": value,
                        "domain": ".skroutz.gr",
                        "path": "/",
                    })

            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                locale='el-GR',
                timezone_id='Europe/Athens',
                permissions=[],
                has_touch=False,
                is_mobile=False,
                device_scale_factor=1,
                java_script_enabled=True,
            )

            # Add cookies if available
            if cookie_list:
                await self.context.add_cookies(cookie_list)

            # Add comprehensive anti-detection scripts
            await self.context.add_init_script("""
                // Override the navigator.webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true
                });

                // Remove automation indicators
                delete navigator.__proto__.webdriver;

                // Override navigator.plugins to make it realistic
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Plugin"
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                            length: 1,
                            name: "Chrome PDF Viewer"
                        },
                        {
                            0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                            1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                            description: "",
                            filename: "internal-nacl-plugin",
                            length: 2,
                            name: "Native Client"
                        }
                    ]
                });

                // Override navigator.languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['el-GR', 'el', 'en-US', 'en']
                });

                // Override Chrome runtime
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // Override permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Add missing properties
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });

                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.'
                });

                // Mock battery API
                Object.defineProperty(navigator, 'getBattery', {
                    value: () => Promise.resolve({
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1
                    })
                });

                // Prevent detection via connection
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 100,
                        downlink: 10,
                        saveData: false
                    })
                });

                // Override mediaDevices
                if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                    const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
                    navigator.mediaDevices.enumerateDevices = () => {
                        return originalEnumerateDevices().then(devices => {
                            return devices.map((device, index) => {
                                return {
                                    deviceId: `device-${index}`,
                                    groupId: `group-${index}`,
                                    kind: device.kind,
                                    label: ''
                                };
                            });
                        });
                    };
                }

                // Canvas fingerprinting protection
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    if (type === 'image/png' && this.width === 16 && this.height === 16) {
                        return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
                    }
                    return originalToDataURL.apply(this, arguments);
                };

                // WebGL fingerprinting protection
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.call(this, parameter);
                };

                // Hide automation via Notification
                const originalPermissions = Notification.permission;
                Object.defineProperty(Notification, 'permission', {
                    get: () => originalPermissions === 'denied' ? 'default' : originalPermissions
                });
            """)

            self.page = await self.context.new_page()

            # Apply playwright-stealth if available
            if STEALTH_AVAILABLE:
                try:
                    await stealth_async(self.page)
                    logger.info("✓ Playwright-stealth applied")
                except Exception as e:
                    logger.warning(f"Could not apply playwright-stealth: {e}")

    async def _save_cookies(self) -> None:
        """Save current cookies to auth manager."""
        if self.context:
            cookies = await self.context.cookies()
            cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
            if cookie_dict:
                self.auth_manager.save_session(
                    cookies=cookie_dict,
                    user_email=self.auth_manager.session.user_email
                )

    async def _wait_for_cloudflare(self, timeout: int = 30000) -> bool:
        """
        Wait for Cloudflare challenge to complete.

        Args:
            timeout: Maximum time to wait in milliseconds

        Returns:
            True if challenge passed, False otherwise
        """
        logger.info("Checking for Cloudflare challenge...")

        try:
            # Wait a bit for page to settle
            await asyncio.sleep(2)

            # Check if we're on a Cloudflare challenge page
            content = await self.page.content()

            # Look for Cloudflare indicators
            cf_indicators = [
                'challenge-platform',
                'cf-browser-verification',
                'cf-challenge',
                'cf-turnstile',
                'Just a moment',
                'Checking your browser',
                'Επαληθεύστε ότι είστε άνθρωπος',
            ]

            is_cloudflare = any(indicator in content for indicator in cf_indicators)

            if is_cloudflare:
                logger.info("Cloudflare challenge detected, attempting to solve...")

                # Try to find and click the Turnstile checkbox
                turnstile_selectors = [
                    'iframe[src*="cloudflare"]',
                    'iframe[src*="turnstile"]',
                    'input[type="checkbox"]',
                    '#cf-turnstile',
                ]

                # Look for Cloudflare iframe
                for selector in turnstile_selectors:
                    try:
                        if 'iframe' in selector:
                            # Handle iframe-based challenge
                            iframe_element = await self.page.query_selector(selector)
                            if iframe_element:
                                logger.info(f"Found Cloudflare iframe: {selector}")
                                # Switch to iframe and try to find checkbox
                                frame = await iframe_element.content_frame()
                                if frame:
                                    checkbox = await frame.query_selector('input[type="checkbox"]')
                                    if checkbox:
                                        logger.info("Clicking Turnstile checkbox...")
                                        await checkbox.click()
                                        await asyncio.sleep(2)
                                        break
                        else:
                            # Direct checkbox
                            checkbox = await self.page.query_selector(selector)
                            if checkbox:
                                logger.info(f"Found checkbox: {selector}")
                                await checkbox.click()
                                await asyncio.sleep(2)
                                break
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue

                # Wait for challenge to complete (URL changes or challenge elements disappear)
                max_wait = timeout / 1000  # Convert to seconds
                waited = 0
                check_interval = 1  # Check every second

                while waited < max_wait:
                    await asyncio.sleep(check_interval)
                    waited += check_interval

                    content = await self.page.content()
                    if not any(indicator in content for indicator in cf_indicators):
                        logger.info("✓ Cloudflare challenge completed")
                        await asyncio.sleep(1)  # Small delay after completion
                        return True

                    # Also check URL - if it changed, challenge might be complete
                    current_url = self.page.url
                    if 'cdn-cgi/challenge' not in current_url:
                        logger.info("✓ Cloudflare challenge passed (URL changed)")
                        await asyncio.sleep(1)
                        return True

                logger.warning("Cloudflare challenge timeout")
                return False
            else:
                logger.info("No Cloudflare challenge detected")
                return True

        except Exception as e:
            logger.error(f"Error waiting for Cloudflare: {e}")
            return False

    async def _human_delay(self, min_ms: int = 100, max_ms: int = 500) -> None:
        """Add a random delay to simulate human behavior."""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

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
            await self._start_browser()

            # Navigate to login page
            logger.info("Navigating to login page...")
            await self.page.goto(f"{self.BASE_URL}/login", wait_until="domcontentloaded")

            # Wait for Cloudflare challenge
            if not await self._wait_for_cloudflare():
                logger.error("Failed to bypass Cloudflare challenge")
                return False

            # Additional wait for page to fully load
            await asyncio.sleep(2)

            # Fill in login form
            logger.info("Filling in login credentials...")

            # Try different possible selectors for email/username field
            email_selectors = [
                'input[name="username"]',
                'input[name="email"]',
                'input[type="email"]',
                'input[id*="email"]',
                'input[id*="username"]',
                'input[placeholder*="email"]',
            ]

            email_filled = False
            for selector in email_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        await self._human_delay(200, 500)
                        await element.click()
                        await self._human_delay(100, 300)
                        await element.fill(credentials.email)
                        logger.info(f"Email filled using selector: {selector}")
                        email_filled = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not email_filled:
                logger.error("Could not find email input field")
                # Save screenshot for debugging
                try:
                    await self.page.screenshot(path="/tmp/skroutz_login_fail_email.png")
                    logger.info("Screenshot saved to /tmp/skroutz_login_fail_email.png")
                except:
                    pass
                return False

            # Click continue button (two-step login flow)
            logger.info("Looking for continue button...")
            continue_selectors = [
                'button:has-text("Συνέχεια")',
                'button:has-text("Continue")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]

            continue_clicked = False
            for selector in continue_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        await self._human_delay(500, 1000)
                        await element.click()
                        logger.info(f"Clicked continue using selector: {selector}")
                        continue_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Continue selector {selector} failed: {e}")
                    continue

            if continue_clicked:
                # Wait for password field to appear
                logger.info("Waiting for password field to appear...")
                await asyncio.sleep(2)
            else:
                logger.info("No continue button found, assuming password field is already visible")

            # Fill password field
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[id*="password"]',
                'input[placeholder*="password"]',
                'input[placeholder*="κωδικός"]',
            ]

            password_filled = False
            for selector in password_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        await self._human_delay(200, 500)
                        await element.click()
                        await self._human_delay(100, 300)
                        await element.fill(credentials.password)
                        logger.info(f"Password filled using selector: {selector}")
                        password_filled = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            if not password_filled:
                logger.error("Could not find password input field")
                try:
                    await self.page.screenshot(path="/tmp/skroutz_login_fail_password.png")
                    logger.info("Screenshot saved to /tmp/skroutz_login_fail_password.png")
                except:
                    pass
                return False

            # Submit the form
            logger.info("Submitting login form...")
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Σύνδεση")',
                'button:has-text("Login")',
                'button:has-text("Είσοδος")',
            ]

            submitted = False
            for selector in submit_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        await self._human_delay(500, 1000)
                        await element.click()
                        logger.info(f"Clicked submit using selector: {selector}")
                        submitted = True
                        break
                except Exception as e:
                    logger.debug(f"Submit selector {selector} failed: {e}")
                    continue

            if not submitted:
                # Try pressing Enter as fallback
                logger.info("Trying Enter key to submit...")
                await self.page.keyboard.press('Enter')

            # Wait for navigation
            await asyncio.sleep(3)

            # Check if login was successful
            current_url = self.page.url
            logger.info(f"Current URL after login: {current_url}")

            # Check for common success indicators
            content = await self.page.content()
            is_logged_in = (
                "/login" not in current_url or
                await self.page.query_selector('a[href*="logout"]') is not None or
                await self.page.query_selector('a[href*="account"]') is not None or
                "logout" in content.lower() or
                "αποσύνδεση" in content.lower()
            )

            if is_logged_in:
                logger.info("✓ Login successful!")

                # Save cookies
                await self._save_cookies()
                self.auth_manager.session.user_email = credentials.email
                self.auth_manager.session.is_authenticated = True
                self.auth_manager._save_session()

                return True
            else:
                logger.error("Login failed - not redirected properly")

                # Check for error messages
                error_elem = await self.page.query_selector('.error, .alert, .message, .error-message')
                if error_elem:
                    error_text = await error_elem.inner_text()
                    logger.error(f"Error message: {error_text}")

                # Save screenshot for debugging
                try:
                    await self.page.screenshot(path="/tmp/skroutz_login_fail.png")
                    logger.info("Screenshot saved to /tmp/skroutz_login_fail.png")
                except:
                    pass

                return False

        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            try:
                await self.page.screenshot(path="/tmp/skroutz_login_error.png")
            except:
                pass
            return False

    async def logout(self) -> None:
        """Logout from skroutz.gr and clear session."""
        try:
            if self.page and self.auth_manager.is_authenticated():
                await self.page.goto(f"{self.BASE_URL}/logout", wait_until="domcontentloaded")
        except Exception:
            pass

        self.auth_manager.clear_session()
        logger.info("Logged out successfully")

    async def search_products(self, query: str) -> list[Product]:
        """
        Search for products by name.

        Args:
            query: Product name or search term

        Returns:
            List of matching products
        """
        logger.info(f"=== SEARCH: query='{query}' ===")

        try:
            await self._start_browser()

            # Navigate to search page
            await self.page.goto(f"{self.BASE_URL}/search?keyphrase={query}", wait_until="domcontentloaded")

            # Wait for Cloudflare
            if not await self._wait_for_cloudflare():
                logger.error("Failed to bypass Cloudflare challenge")
                return []

            await asyncio.sleep(2)

            # Parse products from page
            products = await self._parse_products_from_page()
            logger.info(f"Found {len(products)} products")

            return products

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            return []

    async def add_to_cart(self, product_url: str, quantity: int = 1) -> bool:
        """
        Add a product to the shopping cart.

        Args:
            product_url: Full product URL from search results or SKU ID
            quantity: Quantity to add

        Returns:
            True if successful
        """
        logger.info(f"=== ADD TO CART: url={product_url}, quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            logger.error("Not authenticated")
            raise Exception("Must be authenticated to modify cart")

        try:
            await self._start_browser()

            # Handle both full URLs and SKU IDs
            if product_url.startswith('http'):
                # Full URL provided, use it
                clean_url = product_url.split('?')[0] if '?' in product_url else product_url
                logger.info(f"Navigating to full URL: {clean_url}")
                await self.page.goto(clean_url, wait_until="domcontentloaded")
            else:
                # SKU ID provided, construct URL
                logger.info(f"Navigating to SKU: {product_url}")
                await self.page.goto(f"{self.BASE_URL}/s/{product_url}", wait_until="domcontentloaded")

            if not await self._wait_for_cloudflare():
                logger.error("Cloudflare challenge failed")
                return False
            await asyncio.sleep(2)

            # Find and click add to cart button for "Αγορά μέσω Skroutz"
            add_selectors = [
                'button:has-text("Προσθήκη στο καλάθι")',
                'button:has-text("Αγορά μέσω Skroutz")',
                'button:has-text("Προσθήκη")',
                'a:has-text("Προσθήκη στο καλάθι")',
                'a:has-text("Αγορά μέσω Skroutz")',
                'button[class*="add-to-cart"]',
                'button[class*="add_to_cart"]',
                'button[data-analytics*="cart"]',
            ]

            for selector in add_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        logger.info(f"Found add to cart button with selector: {selector}")

                        # Set quantity if needed
                        qty_input = await self.page.query_selector('input[name="quantity"], input[type="number"]')
                        if qty_input and quantity != 1:
                            await qty_input.fill(str(quantity))
                            await self._human_delay()

                        await self._human_delay(300, 700)
                        await element.click()
                        await asyncio.sleep(3)

                        await self._save_cookies()
                        logger.info("ADD TO CART SUCCESS")
                        return True
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            # Save screenshot for debugging
            try:
                await self.page.screenshot(path="/tmp/skroutz_add_to_cart_fail.png")
                logger.info("Screenshot saved to /tmp/skroutz_add_to_cart_fail.png")
            except:
                pass

            logger.error("Could not find add to cart button")
            return False

        except Exception as e:
            logger.error(f"Add to cart error: {e}", exc_info=True)
            return False

    async def remove_from_cart(self, product_id: str) -> bool:
        """Remove a product from the shopping cart."""
        logger.info(f"=== REMOVE FROM CART: product_id={product_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        try:
            await self._start_browser()
            await self.page.goto(f"{self.BASE_URL}/cart", wait_until="domcontentloaded")
            if not await self._wait_for_cloudflare():
                return False
            await asyncio.sleep(1)

            remove_buttons = await self.page.query_selector_all('button[class*="remove"], a[class*="remove"]')

            for button in remove_buttons:
                await self._human_delay(200, 500)
                await button.click()
                await asyncio.sleep(2)

                await self._save_cookies()
                logger.info("REMOVE FROM CART SUCCESS")
                return True

            logger.warning("Could not find remove button")
            return False

        except Exception as e:
            logger.error(f"Remove from cart error: {e}", exc_info=True)
            return False

    async def update_cart_item_quantity(self, product_id: str, quantity: int) -> bool:
        """Update the quantity of a product in the shopping cart."""
        logger.info(f"=== UPDATE CART: product_id={product_id}, new_quantity={quantity} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to modify cart")

        try:
            await self._start_browser()
            await self.page.goto(f"{self.BASE_URL}/cart", wait_until="domcontentloaded")
            if not await self._wait_for_cloudflare():
                return False
            await asyncio.sleep(1)

            qty_inputs = await self.page.query_selector_all('input[name*="quantity"], input[type="number"]')

            if qty_inputs:
                await qty_inputs[0].fill(str(quantity))
                await self._human_delay(300, 700)

                update_button = await self.page.query_selector('button:has-text("Ενημέρωση"), button:has-text("Update")')
                if update_button:
                    await update_button.click()
                    await asyncio.sleep(2)

                await self._save_cookies()
                logger.info("UPDATE CART SUCCESS")
                return True

            return False

        except Exception as e:
            logger.error(f"Update cart error: {e}", exc_info=True)
            return False

    async def get_cart(self) -> Cart:
        """Get current shopping cart contents."""
        logger.info("=== GET CART ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view cart")

        try:
            await self._start_browser()
            await self.page.goto(f"{self.BASE_URL}/cart", wait_until="domcontentloaded")
            if not await self._wait_for_cloudflare():
                return Cart()
            await asyncio.sleep(1)

            cart = await self._parse_cart_from_page()
            logger.info(f"Cart: item_count={cart.item_count}, total={cart.total}")

            return cart

        except Exception as e:
            logger.error(f"Get cart error: {e}", exc_info=True)
            return Cart()

    async def get_orders(self, include_history: bool = True) -> list[Order]:
        """Get user's orders."""
        logger.info("=== GET ORDERS ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        try:
            await self._start_browser()
            await self.page.goto(f"{self.BASE_URL}/account/orders", wait_until="domcontentloaded")
            if not await self._wait_for_cloudflare():
                return []
            await asyncio.sleep(1)

            orders = await self._parse_orders_from_page()
            logger.info(f"Found {len(orders)} orders")

            if not include_history:
                orders = [
                    o for o in orders
                    if o.status.lower() in ["pending", "confirmed", "processing"]
                ]

            return orders

        except Exception as e:
            logger.error(f"Get orders error: {e}", exc_info=True)
            return []

    async def get_order_details(self, order_id: str) -> Optional[Order]:
        """Get detailed information for a specific order."""
        logger.info(f"=== GET ORDER DETAILS: order_id={order_id} ===")

        if not self.auth_manager.is_authenticated():
            raise Exception("Must be authenticated to view orders")

        try:
            await self._start_browser()
            await self.page.goto(f"{self.BASE_URL}/account/orders/{order_id}", wait_until="domcontentloaded")
            if not await self._wait_for_cloudflare():
                return None
            await asyncio.sleep(1)

            order = await self._parse_order_details_from_page(order_id)
            logger.info(f"Order details retrieved for {order_id}")

            return order

        except Exception as e:
            logger.error(f"Get order details error: {e}", exc_info=True)
            return None

    # Helper methods for parsing

    async def _parse_products_from_page(self) -> list[Product]:
        """Parse products from current page, excluding sponsored/promoted items."""
        from bs4 import BeautifulSoup

        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')
        products = []

        # Save HTML for debugging
        try:
            with open('/tmp/skroutz_search_results.html', 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info("Saved search HTML to /tmp/skroutz_search_results.html")
        except:
            pass

        # Prefer elements with data-skuid attribute
        product_elements = soup.find_all('li', attrs={'data-skuid': True})
        logger.info(f"Found {len(product_elements)} elements with data-skuid")

        if not product_elements:
            # Fallback to class-based parsing
            product_elements = soup.find_all(['li', 'div'], class_=re.compile(r'product|item', re.I))
            logger.info(f"Fallback found {len(product_elements)} product/item elements")

        for elem in product_elements[:50]:
            # Filter out sponsored/promoted products based on uBlock filters
            classes = elem.get('class', [])
            if isinstance(classes, str):
                classes = [classes]

            # Skip labeled/sponsored products (uBlock filter: li.labeled-product.labeled-item)
            if any(cls in classes for cls in ['labeled-product', 'labeled-item', 'product-ad']):
                continue

            # Skip if parent is a sponsored container (uBlock: .selected-product-cards)
            parent = elem.parent
            if parent:
                parent_classes = parent.get('class', [])
                if isinstance(parent_classes, str):
                    parent_classes = [parent_classes]
                if any(cls in parent_classes for cls in ['selected-product-cards', 'product-ad']):
                    continue

            # Skip if has sponsorship/ad attributes
            if elem.get('data-ad') or elem.get('data-sponsored'):
                continue

            try:
                name_elem = elem.find(['a', 'h2', 'h3', 'h4'])
                link_elem = elem.find('a', href=True)

                if not name_elem or not link_elem:
                    continue

                name = name_elem.get_text(strip=True)
                href = link_elem.get('href', '')

                # Extract SKU ID
                product_id = elem.get('data-skuid', '')
                if not product_id:
                    id_match = re.search(r'/s/(\d+)', href)
                    if id_match:
                        product_id = id_match.group(1)

                # Find price with multiple strategies
                price = Decimal("0")
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

                # Fallback: search all text for price
                if price == Decimal("0"):
                    all_text = elem.get_text()
                    price_matches = re.findall(r'([\d.,]+)\s*€', all_text)
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
                availability_text = elem.get_text().lower()
                if any(phrase in availability_text for phrase in ['εξαντλημένο', 'out of stock', 'μη διαθέσιμο']):
                    available = False

                # Find image
                image_elem = elem.find('img')
                image_url = image_elem.get('src') if image_elem else None
                if not image_url and image_elem:
                    image_url = image_elem.get('data-src')

                # Build full URL
                full_url = None
                if href:
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{self.BASE_URL}{href}"

                if name and product_id:
                    product = Product(
                        id=product_id,
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

    async def _parse_cart_from_page(self) -> Cart:
        """Parse cart from current page."""
        from bs4 import BeautifulSoup

        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')
        items = []
        total = Decimal("0")

        cart_items = soup.find_all(['div', 'tr'], class_=re.compile(r'cart.*item', re.I))

        for item_elem in cart_items:
            try:
                name_elem = item_elem.find(['a', 'span', 'h3'])
                price_elem = item_elem.find(['span', 'div'], class_=re.compile(r'price', re.I))
                qty_elem = item_elem.find(['input', 'span'], attrs={'name': re.compile(r'quantity', re.I)})

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

    async def _parse_orders_from_page(self) -> list[Order]:
        """Parse orders from current page."""
        from bs4 import BeautifulSoup

        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')
        orders = []

        order_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'order', re.I))

        for order_elem in order_elements:
            try:
                order_id = ""
                status = "unknown"
                created_at = datetime.now()
                total = Decimal("0")

                id_elem = order_elem.find(['span', 'a'], string=re.compile(r'#?\d+', re.I))
                if id_elem:
                    id_match = re.search(r'(\d+)', id_elem.get_text(strip=True))
                    if id_match:
                        order_id = id_match.group(1)

                status_elem = order_elem.find(['span', 'div'], class_=re.compile(r'status', re.I))
                if status_elem:
                    status = status_elem.get_text(strip=True).lower()

                total_elem = order_elem.find(['span', 'div'], class_=re.compile(r'total', re.I))
                if total_elem:
                    total_text = total_elem.get_text(strip=True)
                    total_match = re.search(r'(\d+[.,]\d+)', total_text.replace('.', '').replace(',', '.'))
                    if total_match:
                        total = Decimal(total_match.group(1))

                if order_id:
                    order = Order(
                        id=order_id,
                        order_number=order_id,
                        status=status,
                        created_at=created_at,
                        total=total,
                    )
                    orders.append(order)

            except Exception as e:
                logger.warning(f"Failed to parse order: {e}")
                continue

        return orders

    async def _parse_order_details_from_page(self, order_id: str) -> Optional[Order]:
        """Parse order details from current page."""
        from bs4 import BeautifulSoup

        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')
        items = []

        item_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'item|product', re.I))

        for item_elem in item_elements:
            try:
                name_elem = item_elem.find(['a', 'span', 'td'])
                if not name_elem:
                    continue

                product_name = name_elem.get_text(strip=True)
                quantity = 1
                price = Decimal("0")

                qty_elem = item_elem.find(['span', 'td'], string=re.compile(r'\d+', re.I))
                if qty_elem:
                    try:
                        quantity = int(re.search(r'\d+', qty_elem.get_text(strip=True)).group())
                    except:
                        pass

                price_elem = item_elem.find(['span', 'td'], class_=re.compile(r'price', re.I))
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d+[.,]\d+)', price_text.replace('.', '').replace(',', '.'))
                    if price_match:
                        price = Decimal(price_match.group(1))

                order_item = OrderItem(
                    product_name=product_name,
                    quantity=quantity,
                    price=price,
                    subtotal=price * quantity,
                )
                items.append(order_item)

            except Exception as e:
                logger.warning(f"Failed to parse order item: {e}")
                continue

        status = "unknown"
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
            order_number=order_id,
            status=status,
            created_at=datetime.now(),
            total=total,
            items=items,
        )

    async def close(self) -> None:
        """Close the browser and cleanup."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
