# Sklavenitis MCP Server

MCP server for [Sklavenitis](https://www.sklavenitis.gr) grocery store with search, cart management, and automatic authentication.

## Features

- 🔐 **Username/Password Authentication** with automatic session persistence
- 🔍 **Product Search** (supports Greek: γάλα, ψωμί, etc.)
- 🛒 **Cart Management** (add products, view cart)
- 💾 **Session Persistence** (cookies saved automatically after login)
- 🚀 **Auto-login** on subsequent runs
- 📦 **2-Step Add-to-Cart** with automatic delivery slot selection

## Installation

```bash
cd sklavenitis-mcp-server
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install mcp curl-cffi pydantic pydantic-settings
```

## Configuration

### Method 1: Environment Variables (Recommended)

Set your credentials as environment variables:

```bash
export SKLAVENITIS_EMAIL="your.email@example.com"
export SKLAVENITIS_PASSWORD="your_password"
```

The server will:
1. Try to login automatically with these credentials
2. Save session cookies to `~/.sklavenitis_session.json`
3. Reuse saved cookies on subsequent runs (no re-login needed)

### Method 2: Manual Cookie Extraction (Fallback)

If automatic login fails due to reCAPTCHA:

1. Login manually at https://www.sklavenitis.gr
2. Open DevTools (F12) → Application → Cookies
3. Copy cookies to `~/.sklavenitis_cookies.json`:

```json
{
  ".AspNet.ApplicationCookie_Frontend4": "YOUR_COOKIE_HERE",
  "__RequestVerificationToken": "YOUR_TOKEN_HERE",
  "StoreSID": "YOUR_STORE_SID_HERE",
  "Zone": "{\"ShippingType\":1,\"HubID\":9}"
}
```

The server will automatically convert these to the new session format.

## Usage

### Running the MCP Server

```bash
python -m sklavenitis_server
```

### Using with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sklavenitis": {
      "command": "python",
      "args": ["-m", "sklavenitis_server"],
      "cwd": "/path/to/sklavenitis-mcp-server",
      "env": {
        "SKLAVENITIS_EMAIL": "your.email@example.com",
        "SKLAVENITIS_PASSWORD": "your_password"
      }
    }
  }
}
```

## Available Tools

### `sklavenitis_search_products`
Search for products by name (supports Greek).

**Parameters:**
- `query` (required): Search term (e.g., "γάλα", "ψωμί", "milk")

### `sklavenitis_add_to_cart`
Add product to cart with automatic delivery slot selection (next day 7-9am).

**Parameters:**
- `product_sku` (required): Product SKU from search results
- `quantity` (optional): Quantity to add (default: 1)

### `sklavenitis_get_cart`
View current shopping cart contents.

**Parameters:** None

### `sklavenitis_login`
Manually trigger login (usually not needed - happens automatically).

**Parameters:**
- `email` (optional): Email if not configured via environment
- `password` (optional): Password if not configured via environment

### `sklavenitis_logout`
Logout and clear session.

**Parameters:** None

## Example Usage

```
User: Search for milk in Sklavenitis
Claude: [Uses sklavenitis_search_products with query="γάλα"]

Found 21 products:
1. ΙΟΝ Γάλακτος Σοκολάτα 100g (SKU: 1631417)
2. ΜΕΒΓΑΛ Γιαούρτι... (SKU: 1666513)
...

User: Add the first one to my cart
Claude: [Uses sklavenitis_add_to_cart with product_sku="1631417"]

✅ Successfully added product 1631417 to cart
Delivery slot: Tomorrow 7:00-9:00 AM

User: Show me my cart
Claude: [Uses sklavenitis_get_cart]

Shopping Cart (1 items):
Total: €1,09
Delivery: Friday 24/10/2025, 07:00 - 09:00

Items:
  - SKU 1631417: Quantity 1.00
```

## Testing

Run integration tests:

```bash
python test_client.py
```

This will:
- Try to login (or use existing session)
- Search for "γάλα"
- Add a product to cart
- Verify cart contents

## How It Works

### Authentication Flow

1. **First Run:** Server tries to login with username/password
   - If successful: Saves cookies to `~/.sklavenitis_session.json`
   - If fails (reCAPTCHA): User can manually extract cookies

2. **Subsequent Runs:** Server loads saved cookies automatically
   - No re-login needed
   - Cookies typically valid for days/weeks

### Add-to-Cart Process

Adding to cart requires **2 steps** (both handled automatically):

1. POST to add product (SKU + quantity)
2. POST to select delivery slot (auto-selects next day 7-9am)

If step 2 is skipped, items won't appear in cart - this is handled correctly by the client.

## Troubleshooting

### "Login failed - no auth cookie received"

This is expected due to reCAPTCHA enforcement. Use manual cookie extraction (Method 2).

### "Cart is empty" after adding items

Make sure you're using the latest version - older versions didn't complete the 2-step add-to-cart process.

### Cookies expired

Delete `~/.sklavenitis_session.json` and the server will re-login automatically.

## Technical Details

- **HTTP Client:** curl-cffi with Chrome 120 impersonation
- **Session Storage:** `~/.sklavenitis_session.json`
- **Default Delivery:** Tomorrow 7:00-9:00 AM, Hub ID 9 (Athens area)
- **Language:** Greek (el-GR)

## License

MIT

