# Sklavenitis MCP Server

MCP (Model Context Protocol) server for interacting with [sklavenitis.gr](https://www.sklavenitis.gr), a Greek online grocery store.

## Features

- **Authentication**: Login and logout functionality
- **Product Search**: Search for products by name or EAN/barcode
- **Shopping Cart**: Add, remove, update quantities, and view cart contents
- **Orders**: View past and current orders
- **Session Management**: Automatic session persistence and re-authentication

## Installation

```bash
# Clone the repository
cd sklavenitis-mcp-server

# Install dependencies using uv
uv sync

# Or install with pip
pip install -e .
```

## Configuration

The server can be configured with environment variables for automatic authentication:

```bash
export SKLAVENITIS_EMAIL="your-email@example.com"
export SKLAVENITIS_PASSWORD="your-password"
```

### Claude Desktop Configuration

Add to your Claude desktop configuration file:

**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sklavenitis": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/sklavenitis-mcp-server",
        "run",
        "sklavenitis-server"
      ],
      "env": {
        "SKLAVENITIS_EMAIL": "your-email@example.com",
        "SKLAVENITIS_PASSWORD": "your-password"
      }
    }
  }
}
```

## Available Tools

### `sklavenitis_login`
Authenticate with sklavenitis.gr. If environment variables are set, authentication happens automatically.

**Parameters:**
- `email` (optional): User email
- `password` (optional): User password

### `sklavenitis_logout`
Logout and clear session.

### `sklavenitis_search_products`
Search for products by name or EAN.

**Parameters:**
- `query` (optional): Product name or search term
- `ean` (optional): EAN/barcode for exact match

### `sklavenitis_add_to_cart`
Add a product to the shopping cart (requires authentication).

**Parameters:**
- `product_id` (required): Product ID
- `quantity` (optional): Quantity to add (default: 1)

### `sklavenitis_remove_from_cart`
Remove a product from the cart (requires authentication).

**Parameters:**
- `product_id` (required): Product ID to remove

### `sklavenitis_update_cart_quantity`
Update product quantity in cart (requires authentication).

**Parameters:**
- `product_id` (required): Product ID
- `quantity` (required): New quantity

### `sklavenitis_get_cart`
Get current shopping cart contents (requires authentication).

### `sklavenitis_get_orders`
Get user's orders (requires authentication).

**Parameters:**
- `include_history` (optional): Include past orders (default: true)

## Resources

When authenticated, the following resources are available:

- `sklavenitis://cart` - Current shopping cart contents
- `sklavenitis://orders` - User's orders

## Architecture

The server is built using:
- **MCP SDK**: For Model Context Protocol communication
- **httpx**: For HTTP requests to sklavenitis.gr
- **BeautifulSoup**: For HTML parsing
- **Pydantic**: For data validation and modeling

### Key Components

- `sklavenitis_client.py`: Core client for interacting with sklavenitis.gr
- `auth.py`: Authentication and session management
- `models.py`: Data models for products, cart, orders
- `server.py`: MCP server implementation

## Implementation Notes

### Authentication Flow

Sklavenitis.gr uses Atcom Yoda CMS with the following authentication mechanism:

1. Visit homepage to establish session
2. GET login form to retrieve CSRF token (`__RequestVerificationToken`)
3. POST credentials with CSRF token to `/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/`
4. Verify login by checking for logout button on account page

The site includes ReCAPTCHA but it's not enforced on first login attempt, making automated authentication possible for legitimate use cases.

### API Endpoints

- **Login**: `/ajax/Atcom.Sites.Yoda.Components.UserFlow.LoginUserFlow.Index/`
- **Logout**: `/ajax/Atcom.Sites.Yoda.Components.Account.LogOut/`
- **Search**: `/ajax/Atcom.Sites.Yoda.Components.Search.Index/` (returns HTML with analytics JSON)
- **Cart**: `/ajax/Atcom.Sites.Yoda.Components.Cart.Index/?View=MiniCart`
- **Add to Cart**: `/ajax/Atcom.Sites.Yoda.Components.UserFlow.AddToCartUserFlow.Index/`
- **Orders**: `/account/paraggelvies`

## Development

### Running Tests

```bash
# Test login
uv run python test_full_client.py

# Test with environment variables
SKLAVENITIS_EMAIL="email" SKLAVENITIS_PASSWORD="password" uv run python test_full_client.py
```

### Project Structure

```
sklavenitis-mcp-server/
├── sklavenitis_server/
│   ├── __init__.py
│   ├── __main__.py
│   ├── auth.py              # Authentication manager
│   ├── cli.py               # CLI entry point
│   ├── models.py            # Data models
│   ├── sklavenitis_client.py # Core client
│   └── server.py            # MCP server
├── pyproject.toml           # Project configuration
├── README.md               # This file
└── test_*.py               # Test scripts
```

## Limitations

### Cart Operations Require Initial Web Setup

**Important**: Before cart operations will work via the API, you must configure your delivery address once through the Sklavenitis website:

1. Log in to [sklavenitis.gr](https://www.sklavenitis.gr) in a web browser
2. Navigate to your account and set up your delivery address (e.g., "Σύμης 4, 15127")
3. This address configuration persists in your account
4. Once configured, all API operations (add to cart, update quantity, remove) work correctly

**Technical Details**:
- The API will return `{"Result": 4}` when attempting cart operations without address setup
- Address validation requires web interface (includes map/geocoding functionality)
- After initial setup, `set_delivery_timeslot()` and cart operations work via API
- The address remains associated with your account for all future API sessions

### Other Limitations

- Cart and order parsing relies on HTML structure, which may change
- ReCAPTCHA may be enforced after multiple failed login attempts

## License

This project is for educational and personal use only. Please respect sklavenitis.gr's terms of service.

## Related Projects

- [efresh-mcp-server](../efresh-mcp-server) - MCP server for e-fresh.gr
