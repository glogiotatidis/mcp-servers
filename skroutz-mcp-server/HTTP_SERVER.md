# Skroutz MCP HTTP Server API

REST API server for Skroutz.gr with interactive documentation.

## Starting the Server

### With Docker
```bash
docker-compose up skroutz-http
```

### Locally
```bash
python -m skroutz_server.cli --mode http
```

### With Hot Reloading (Development)
```bash
python -m skroutz_server.cli --mode http --reload
```

Server runs on `http://localhost:8000`

## Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Health Check
```bash
GET /health

curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "authenticated": false
}
```

### Authentication

#### Login
```bash
POST /auth/login

curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com", "password": "password"}'
```

#### Check Status
```bash
GET /auth/status

curl http://localhost:8000/auth/status
```

#### Logout
```bash
POST /auth/logout

curl -X POST http://localhost:8000/auth/logout
```

### Product Search

```bash
POST /products/search

curl -X POST http://localhost:8000/products/search \
  -H "Content-Type: application/json" \
  -d '{"query": "ddr5 64gb memory"}'
```

Response:
```json
{
  "count": 24,
  "products": [
    {
      "id": "58480801",
      "name": "Kingston Valueram 32GB DDR5",
      "price": "136.87",
      "available": true,
      "url": "https://www.skroutz.gr/s/58480801/..."
    }
  ]
}
```

### Cart Operations

#### Get Cart
```bash
GET /cart

curl http://localhost:8000/cart
```

#### Add to Cart
```bash
POST /cart/add

curl -X POST http://localhost:8000/cart/add \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PRODUCT_URL", "quantity": 1}'
```

**Note**: Use the full URL from search results for best results.

#### Update Quantity
```bash
POST /cart/update

curl -X POST http://localhost:8000/cart/update \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PRODUCT_ID", "quantity": 2}'
```

#### Remove from Cart
```bash
POST /cart/remove

curl -X POST http://localhost:8000/cart/remove \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PRODUCT_ID"}'
```

### Orders

#### Get Orders
```bash
POST /orders

curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{"include_history": true}'
```

#### Get Order Details
```bash
GET /orders/{order_id}

curl http://localhost:8000/orders/ORDER_ID
```

## Request/Response Models

### SearchRequest
```json
{
  "query": "string"
}
```

### AddToCartRequest
```json
{
  "product_id": "string (URL or SKU ID)",
  "quantity": 1
}
```

### UpdateCartRequest
```json
{
  "product_id": "string",
  "quantity": 1
}
```

## Environment Variables

Configure via environment or `.env` file:

```bash
SKROUTZ_EMAIL=your-email@example.com
SKROUTZ_PASSWORD=your-password
```

## Development

### Hot Reloading

Run with `--reload` flag for automatic reloading on file changes:

```bash
python -m skroutz_server.cli --mode http --reload
```

Changes to any file in `skroutz_server/` will trigger automatic reload.

### Custom Port

```bash
python -m skroutz_server.cli --mode http --port 3000
```

## Notes

- Cart operations use Playwright browser automation (may take a few seconds)
- Search operations use curl_cffi (fast response)
- Not all products support "Αγορά μέσω Skroutz" direct purchasing
- Session persists across requests
