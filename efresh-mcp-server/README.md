# E-Fresh MCP Server

An MCP (Model Context Protocol) server for interacting with [e-fresh.gr](https://www.e-fresh.gr), a Greek online grocery store. This server allows you to search products, manage your shopping cart, and view orders through Claude or other MCP-compatible clients, or via HTTP REST API.

## Features

- **Authentication**: Login and logout from e-fresh.gr
- **Product Search**: Search products by name or EAN/barcode
- **Shopping Cart**: Add, remove, and view cart contents
- **Order Management**: View current and past orders
- **Multi-language**: Support for Greek (default) and English
- **Session Persistence**: Automatic session management with secure credential storage
- **Dual Interface**: Works as both MCP stdio server and HTTP REST API

## Installation

### Prerequisites

- Python 3.10 or higher
- pip

### Setup

1. Clone or navigate to the project directory:

```bash
cd efresh-mcp-server
```

2. Create a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package:

```bash
pip install -e .
```

### Docker Installation

The server can also run in Docker using Docker Compose:

1. Create a `.env` file in the project root with your credentials:

```bash
EFRESH_EMAIL=your-email@example.com
EFRESH_PASSWORD=your-password
```

2. Build and run with Docker Compose:

```bash
docker-compose up -d
```

The HTTP API will be available at `http://localhost:8000`.

**Docker Commands:**
```bash
# Start the server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the server
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

## Configuration

### Claude Desktop

To use this MCP server with Claude Desktop, add the following to your Claude configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "efresh": {
      "command": "python",
      "args": ["-m", "efresh_server"],
      "env": {
        "EFRESH_EMAIL": "your-email@example.com",
        "EFRESH_PASSWORD": "your-password"
      }
    }
  }
}
```

If you're using a virtual environment, use the full path to the Python interpreter:

```json
{
  "mcpServers": {
    "efresh": {
      "command": "/full/path/to/venv/bin/python",
      "args": ["-m", "efresh_server"],
      "env": {
        "EFRESH_EMAIL": "your-email@example.com",
        "EFRESH_PASSWORD": "your-password"
      }
    }
  }
}
```

### Cursor

For Cursor, add to your MCP settings file at:

**macOS**: `~/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

```json
{
  "mcpServers": {
    "efresh": {
      "type": "stdio",
      "command": "/full/path/to/.venv/bin/python",
      "args": ["-m", "efresh_server"],
      "env": {
        "EFRESH_EMAIL": "your-email@example.com",
        "EFRESH_PASSWORD": "your-password"
      }
    }
  }
}
```

**Important**:
- Replace `/full/path/to/.venv/bin/python` with the actual path to your Python interpreter
- Replace `your-email@example.com` and `your-password` with your e-fresh.gr credentials
- **Passwords with special characters**: If your password contains special characters (like `$`, `;`, `\`, etc.), they work fine in JSON configuration files - no escaping needed
- After updating the configuration, restart Claude Desktop or Cursor

### Environment Variables

The server supports automatic authentication via environment variables:

- `EFRESH_EMAIL` - Your e-fresh.gr email (required for auto-login)
- `EFRESH_PASSWORD` - Your e-fresh.gr password (required for auto-login)

When these are configured, cart and order operations will automatically log in before executing.

### Testing Credentials

For development and testing, you can store credentials in `.env.local`:

```bash
EFRESH_EMAIL=your-email@example.com
EFRESH_PASSWORD=your-password
```

**Important**:
- Never commit `.env.local` or any file containing credentials to version control
- **Shell escaping**: When passing passwords via command line with special characters (like `$`, `;`, `\`), use single quotes to prevent shell interpretation:
  ```bash
  # CORRECT - single quotes prevent expansion
  EFRESH_PASSWORD='MyP@ss$123;' python -m efresh_server

  # WRONG - double quotes allow $ expansion
  EFRESH_PASSWORD="MyP@ss$123;"  # $123 gets expanded as a variable!
  ```

## Usage

The server can run in two modes:

1. **stdio mode** (default): For MCP clients like Claude Desktop/Cursor
2. **http mode**: REST API server with interactive documentation

### Running the Server

**MCP stdio mode (for Claude/Cursor):**
```bash
python -m efresh_server
# or
efresh-server
```

**HTTP API mode:**
```bash
python -m efresh_server.cli --mode http
# or with environment variables
EFRESH_EMAIL="your-email" EFRESH_PASSWORD="your-password" python -m efresh_server.cli --mode http --host 0.0.0.0 --port 8000
```

The HTTP API provides:
- Interactive documentation at `http://localhost:8000/docs`
- ReDoc documentation at `http://localhost:8000/redoc`
- OpenAPI schema at `http://localhost:8000/openapi.json`

**HTTP Server MCP Configuration** (for debugging):
```json
{
  "mcpServers": {
    "efresh-http": {
      "command": "/full/path/to/.venv/bin/python",
      "args": ["-m", "efresh_server.cli", "--mode", "http", "--port", "8000"],
      "env": {
        "EFRESH_EMAIL": "your-email@example.com",
        "EFRESH_PASSWORD": "your-password"
      }
    }
  }
}
```

**Note**: HTTP mode is primarily for testing/debugging. For normal usage, use stdio mode.

### HTTP API Endpoints

When running in HTTP mode, the following endpoints are available:

**Authentication:**
- `POST /auth/login` - Login with email and password
- `POST /auth/logout` - Logout and clear session
- `GET /auth/status` - Check authentication status

**Products:**
- `POST /products/search` - Search products by name or EAN

**Cart:**
- `GET /cart` - Get current cart
- `POST /cart/add` - Add product to cart
- `POST /cart/remove` - Remove product from cart

**Orders:**
- `POST /orders` - Get user's orders

**Settings:**
- `GET /settings/language` - Get current language
- `POST /settings/language` - Set language (el/en)

**Other:**
- `GET /health` - Health check
- `GET /mcp/tools` - List available MCP tools

### MCP Tools (stdio mode)

Once configured, the following tools will be available in Claude:

#### `efresh_login`
Authenticate with e-fresh.gr. Uses credentials from environment if not provided.

```
Parameters (all optional if environment variables are configured):
- email: User email address (uses EFRESH_EMAIL if not provided)
- password: User password (uses EFRESH_PASSWORD if not provided)
```

**Note**:
- If you configured `EFRESH_EMAIL` and `EFRESH_PASSWORD` in the MCP settings, you can call this tool without any parameters
- Cart and order operations automatically authenticate when needed, so manual login is optional
- Use this tool explicitly if you want to verify credentials or switch accounts

#### `efresh_logout`
Logout from e-fresh.gr and clear the session.

#### `efresh_search_products`
Search for products by name or EAN/barcode.

```
Parameters:
- query: Product name or search term (optional)
- ean: EAN/barcode for exact match (optional)
```

#### `efresh_add_to_cart`
Add a product to the shopping cart.

```
Parameters:
- product_id: Product ID (from search results)
- quantity: Quantity to add (default: 1)
```

**Note**: Automatically logs in using configured credentials if not already authenticated.

#### `efresh_remove_from_cart`
Remove a product from the shopping cart.

```
Parameters:
- product_id: Product ID to remove
```

**Note**: Automatically logs in using configured credentials if not already authenticated.

#### `efresh_update_cart_quantity`
Update the quantity of a product in the shopping cart.

```
Parameters:
- product_id: Product ID to update (required)
- quantity: New quantity to set (required)
```

**Note**:
- Automatically logs in using configured credentials if not already authenticated.
- This sets the quantity to the specified value (does not add to existing quantity).
- To remove an item, use `efresh_remove_from_cart` instead of setting quantity to 0.

#### `efresh_get_cart`
Get current shopping cart contents with all items and total.

**Note**: Automatically logs in using configured credentials if not already authenticated.

#### `efresh_get_orders`
Get user's orders. Can optionally include full item details for each order.

```
Parameters:
- include_history: Include past orders (default: true)
- include_items: Fetch full order details including items for each order (default: false)
```

**Note**:
- Automatically logs in using configured credentials if not already authenticated.
- Set `include_items=true` to fetch all items for each order. This makes additional API calls but provides complete order information.

#### `efresh_get_order_details`
Get detailed information for a specific order, including all items.

```
Parameters:
- order_id: Order ID to fetch details for (required)
```

**Note**: Automatically logs in using configured credentials if not already authenticated.

#### `efresh_set_language`
Set the interface language.

```
Parameters:
- language: 'el' for Greek, 'en' for English
```

### Example Workflow

Here's an example conversation with Claude using this MCP server:

```
User: Login to e-fresh with my credentials

Claude: [Uses efresh_login tool]

User: Search for "φέτα" (feta cheese)

Claude: [Uses efresh_search_products with query="φέτα"]
Found 12 products:
1. DODONI Φέτα ΠΟΠ...
   ID: 12345
   ...

User: Add product 12345 to my cart

Claude: [Uses efresh_add_to_cart with product_id="12345"]

User: Show me my cart

Claude: [Uses efresh_get_cart]
Shopping Cart (1 items):
...

User: Show me my past orders with all items

Claude: [Uses efresh_get_orders with include_items=true]
Found 10 orders:

1. Order #25052221550794718983
   Status: completed
   Date: 2025-05-22 21:55
   Total: €24.51
   Items (8):
     - ΤΣΙΠΣ COUNTRY ΑΛΑΤΙ JUMBO 150Γ x3 (€4.23)
     - ΤΣΙΠΣ COUNTRY ΠΙΠΕΡΙ JUMBO 150Γ x3 (€4.29)
     ...

User: Get full details for order 25052221550794718983

Claude: [Uses efresh_get_order_details with order_id="25052221550794718983"]
Order Details:

Order #25052221550794718983
Status: completed
Date: 2025-05-22 21:55
Total: €24.51

Items (8):
1. ΤΣΙΠΣ COUNTRY ΑΛΑΤΙ JUMBO 150Γ
   Quantity: 3
   Price: €1.41
   Subtotal: €4.23
...
```

## Available Resources

When authenticated, the server provides the following MCP resources:

- `efresh://cart` - Current shopping cart contents (JSON)
- `efresh://orders` - User's orders (JSON)

These resources can be accessed by Claude to get real-time information about your cart and orders.

## Architecture

The server consists of several modules:

- `server.py`: MCP server implementation with tool handlers
- `efresh_client.py`: HTTP client for interacting with e-fresh.gr API
- `auth.py`: Authentication and session management
- `models.py`: Pydantic data models for products, cart, orders, etc.

### Session Management

Sessions are automatically persisted to `~/.efresh_session.json` after successful login. This file contains:
- Session cookies
- User email
- Authentication status

The session file is created with restrictive permissions (0600) for security.

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Code Formatting

```bash
black efresh_server/
```

### Type Checking

```bash
mypy efresh_server/
```

## Troubleshooting

### Debugging with Logs

The server now includes comprehensive logging for all operations. Check the logs for detailed information:

**View logs when running tests:**
```bash
EFRESH_EMAIL="your-email" EFRESH_PASSWORD="your-password" uv run python test_login_env.py 2>&1 | grep "INFO\|ERROR"
```

**Log files location:**
- **Claude Desktop**: `~/Library/Logs/Claude/mcp*.log`
- **Cursor**: Check developer console or MCP output panel
- **HTTP mode**: Terminal output

See [LOGGING_DEBUG.md](./LOGGING_DEBUG.md) for detailed debugging information.

### Cart Shows Empty

If your cart appears empty after adding items:

1. **Check the logs** for authentication status and cookie counts
2. **Verify environment variables** are set in MCP configuration:
   ```bash
   # Should see these in logs:
   INFO:efresh_server.efresh_client:=== ADD TO CART ===
   INFO:efresh_server.efresh_client:API cart total_qty: 2
   INFO:efresh_server.efresh_client:ADD TO CART SUCCESS via API
   ```
3. **Restart your MCP client** (Claude Desktop/Cursor) after config changes
4. **Clear old session** if needed:
   ```bash
   rm ~/.efresh_session.json
   ```

### Authentication Issues

If login fails:
1. Verify your credentials are correct
2. Check if e-fresh.gr is accessible from your network
3. Try logging in through a web browser to ensure your account is active
4. Check the session file: `~/.efresh_session.json`
5. Look for login errors in the logs:
   ```
   ERROR:efresh_server.efresh_client:Login failed: Invalid credentials
   ```

### Connection Issues

If you get connection errors:
1. Check your internet connection
2. Verify e-fresh.gr is not blocking your IP
3. Check if you need to go through a proxy

### Session Expiration

If your session expires:
1. Simply use the `efresh_login` tool again
2. The server will automatically refresh your session

## API Reverse Engineering

This server works by:
1. Making HTTP requests to e-fresh.gr endpoints
2. Parsing HTML/JSON responses
3. Managing cookies for session persistence

The server attempts to use API endpoints where available, falling back to HTML parsing when necessary.

## Security Considerations

- Never commit credentials to version control
- Session files are stored with restrictive permissions
- Use HTTPS for all requests to e-fresh.gr
- Consider using environment variables for credentials in production

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Disclaimer

This is an unofficial client for e-fresh.gr. Use at your own risk. The authors are not affiliated with or endorsed by e-fresh.gr.
