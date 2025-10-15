# Skroutz MCP Server

MCP (Model Context Protocol) server for [Skroutz.gr](https://www.skroutz.gr), Greece's leading price comparison platform. Search products, manage shopping cart, and view orders through Claude or other MCP-compatible clients.

## Features

- **Product Search**: Fast product search with price, availability, and URL information
- **Shopping Cart**: Add, remove, and view cart items (supports "Αγορά μέσω Skroutz")
- **Order Management**: View current and past orders
- **Dual Mode**: Run as stdio MCP server or HTTP REST API
- **Docker Support**: Easy deployment with Docker Compose
- **Session Persistence**: Automatic authentication and cookie management

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose
- Skroutz.gr account

### Run with Docker

1. Create `.env` file:
```bash
SKROUTZ_EMAIL=your@email.com
SKROUTZ_PASSWORD=your-password
```

2. Start HTTP server:
```bash
docker-compose up skroutz-http
```

3. Or stdio server:
```bash
docker-compose up skroutz-stdio
```

4. HTTP API available at: `http://localhost:8000`
   - Docs: http://localhost:8000/docs

## Local Installation

```bash
# Install dependencies
pip install -e .

# Run stdio mode
python -m skroutz_server

# Run HTTP mode
python -m skroutz_server.cli --mode http

# Run with hot reloading (development)
python -m skroutz_server.cli --mode http --reload
```

## Configuration for MCP Clients

### Cursor/Claude Desktop

Add to `~/.cursor/mcp.json` or `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "skroutz": {
      "command": "python",
      "args": ["-m", "skroutz_server"],
      "env": {
        "SKROUTZ_EMAIL": "your@email.com",
        "SKROUTZ_PASSWORD": "your-password"
      }
    }
  }
}
```

Or with Docker:
```json
{
  "mcpServers": {
    "skroutz": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
               "-e", "SKROUTZ_EMAIL=your@email.com",
               "-e", "SKROUTZ_PASSWORD=your-password",
               "skroutz-mcp-server"]
    }
  }
}
```

## Available Tools

### `skroutz_search_products`
Search for products.

**Parameters:**
- `query` (required): Search term

**Returns:** Products with price, availability, URLs

**Example:**
```
Search for "ddr5 64gb memory"
```

### `skroutz_add_to_cart`
Add product to cart.

**Parameters:**
- `product_id` (required): Product URL from search results
- `quantity` (optional): Quantity (default: 1)

**Note:** Use full product URL from search results. Only works for products supporting "Αγορά μέσω Skroutz".

### `skroutz_remove_from_cart`
Remove item from cart.

**Parameters:**
- `product_id` (required): Line item ID from cart

**Note:** Use the `id` field from cart items (line_item_id).

### `skroutz_update_cart_quantity`
Update item quantity.

**Parameters:**
- `product_id` (required): Line item ID
- `quantity` (required): New quantity

### `skroutz_get_cart`
View cart contents.

### `skroutz_get_orders`
Get orders.

**Parameters:**
- `include_history` (optional): Include past orders (default: true)

### `skroutz_get_order_details`
Get order details.

**Parameters:**
- `order_id` (required): Order ID

### `skroutz_login` / `skroutz_logout`
Manual authentication (optional if credentials in environment).

## HTTP API

See [HTTP_SERVER.md](HTTP_SERVER.md) for complete HTTP API documentation.

### Quick Examples

```bash
# Search
curl -X POST http://localhost:8000/products/search \
  -H "Content-Type: application/json" \
  -d '{"query": "usb 32gb"}'

# Add to cart (use URL from search results)
curl -X POST http://localhost:8000/cart/add \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PRODUCT_URL", "quantity": 1}'

# Get cart
curl http://localhost:8000/cart

# Remove from cart (use line_item_id from cart)
curl -X POST http://localhost:8000/cart/remove \
  -H "Content-Type: application/json" \
  -d '{"product_id": "LINE_ITEM_ID"}'
```

## Architecture

- **curl_cffi**: All operations use curl_cffi for Cloudflare bypass
- **Session Management**: Cookies stored in `~/.skroutz_session.json`
- **Anti-Ad Filter**: Excludes sponsored/promoted products from search results

## Development

```bash
# Hot reloading mode
python -m skroutz_server.cli --mode http --reload

# Custom port
python -m skroutz_server.cli --mode http --port 3000 --reload
```

Changes to files in `skroutz_server/` auto-reload instantly.

## Docker Build

```bash
# Build image
docker-compose build

# Run HTTP server
docker-compose up skroutz-http

# Run stdio server
docker-compose up skroutz-stdio

# View logs
docker-compose logs -f
```

## Notes

- **Cloudflare Protection**: Uses curl_cffi with Chrome impersonation
- **Cart Operations**: Only work for products with "Αγορά μέσω Skrουtz" support
- **Search**: Filters out sponsored/promoted products automatically
- **Session**: Persists across restarts via volume mounts in Docker

## Troubleshooting

### Authentication Fails
- Verify credentials are correct
- Check `~/.skroutz_session.json` for valid cookies
- Try manual login via browser and extract cookies if needed

### Cart Operations Fail
- Product may not support "Αγορά μέσω Skroutz"
- Try a different product
- Check product page manually on Skroutz.gr

### Search Returns No Results
- Cloudflare may be rate-limiting
- Wait a few minutes and try again
- Cookies may need refresh - try logout/login

## License

MIT License

## Disclaimer

Unofficial client for Skroutz.gr. Not affiliated with or endorsed by Skroutz.
