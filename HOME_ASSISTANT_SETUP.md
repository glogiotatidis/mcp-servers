# Home Assistant MCP Integration Setup

This guide explains how to set up the Skroutz and E-Fresh MCP servers with Home Assistant using Docker and mcp-proxy.

## Overview

Home Assistant's MCP integration requires an SSE (Server-Sent Events) endpoint. Our MCP servers use stdio communication by default, so we use `mcp-proxy` to bridge them to SSE for Home Assistant compatibility.

## Architecture

```
Home Assistant → SSE (http://localhost:8080/sse) → mcp-proxy → stdio → Skroutz MCP Server
Home Assistant → SSE (http://localhost:8081/sse) → mcp-proxy → stdio → E-Fresh MCP Server
```

## Prerequisites

- Docker and Docker Compose installed
- Home Assistant with MCP integration enabled
- Valid credentials for Skroutz.gr and/or E-Fresh.gr

## Setup Steps

### 1. Configure Environment Variables

Copy the example compose file and create your `.env` file:

```bash
cd skroutz-mcp-server
cp docker-compose.example.yml docker-compose.yml
```

Create `.env` file:

```bash
# .env for Skroutz
SKROUTZ_EMAIL=your@email.com
SKROUTZ_PASSWORD=your-password
```

Repeat for E-Fresh:

```bash
cd ../efresh-mcp-server
cp docker-compose.example.yml docker-compose.yml
```

Create `.env` file:

```bash
# .env for E-Fresh
EFRESH_EMAIL=your@email.com
EFRESH_PASSWORD=your-password
```

### 2. Build and Start Docker Containers

```bash
# Start Skroutz MCP server
cd skroutz-mcp-server
docker-compose up -d --build

# Start E-Fresh MCP server
cd ../efresh-mcp-server
docker-compose up -d --build
```

### 3. Verify Services

Check that the SSE endpoints are accessible:

```bash
# Skroutz SSE endpoint
curl http://localhost:8080/health

# E-Fresh SSE endpoint
curl http://localhost:8081/health
```

### 4. Configure Home Assistant

Add the MCP servers to your Home Assistant `configuration.yaml`:

```yaml
mcp:
  servers:
    - name: "Skroutz"
      url: "http://localhost:8080/sse"
      description: "Greek e-commerce platform"
      
    - name: "E-Fresh"
      url: "http://localhost:8081/sse"
      description: "Greek online grocery store"
```

### 5. Restart Home Assistant

Restart Home Assistant to load the new MCP configuration:

```bash
# Via Home Assistant UI:
# Settings → System → Restart
```

## Verification

After restarting Home Assistant, you should see the MCP servers in:
- **Developer Tools → Actions** (formerly Services)
- Look for actions starting with `mcp.skroutz_*` and `mcp.efresh_*`

## Available Actions

### Skroutz Actions
- `mcp.skroutz_search_products` - Search for products
- `mcp.skroutz_add_to_cart` - Add items to cart
- `mcp.skroutz_get_cart` - View cart contents
- `mcp.skroutz_empty_cart` - Clear cart
- `mcp.skroutz_get_orders` - List orders
- `mcp.skroutz_get_order_details` - Get order details

### E-Fresh Actions
- `mcp.efresh_search_products` - Search for products
- `mcp.efresh_add_to_cart` - Add items to cart
- `mcp.efresh_get_cart` - View cart contents
- `mcp.efresh_get_orders` - List orders

## Troubleshooting

### Connection Errors

1. Check Docker containers are running:
   ```bash
   docker ps
   ```

2. View container logs:
   ```bash
   docker logs skroutz-mcp-server
   docker logs efresh-mcp-server
   ```

3. Verify network connectivity:
   ```bash
   curl http://localhost:8080/sse
   curl http://localhost:8081/sse
   ```

### Authentication Issues

If you see authentication errors:

1. Verify credentials in `.env` files
2. Restart containers:
   ```bash
   docker-compose restart
   ```

### Session Persistence

Sessions are persisted in Docker volumes:
- Skroutz: `session-data` volume at `/home/skroutz/.skroutz-mcp`
- E-Fresh: `session-data` volume at `/root/.efresh-mcp`

To clear sessions:

```bash
# Stop containers
docker-compose down

# Remove volumes
docker volume rm skroutz-mcp-server_session-data
docker volume rm efresh-mcp-server_session-data

# Restart
docker-compose up -d
```

## Advanced Configuration

### Custom Ports

To use different ports, edit `docker-compose.yml`:

```yaml
ports:
  - "9080:8080"  # Change host port (9080) but keep container port (8080)
```

Then update Home Assistant configuration to use the new port.

### Running Without Docker

If you prefer to run without Docker:

1. Install Node.js and npm
2. Install mcp-proxy:
   ```bash
   npm install -g @chrishayuk/mcp-proxy
   ```

3. Install Python dependencies:
   ```bash
   cd skroutz-mcp-server
   pip install -e .
   ```

4. Run with mcp-proxy:
   ```bash
   export SKROUTZ_EMAIL=your@email.com
   export SKROUTZ_PASSWORD=your-password
   mcp-proxy --stdio "python -m skroutz_server" --port 8080 --host 0.0.0.0
   ```

## Security Considerations

1. **Network Security**: The SSE endpoints are accessible on your local network. Consider using:
   - Docker network isolation
   - Firewall rules
   - Reverse proxy with authentication

2. **Credentials**: Keep `.env` files secure:
   - Never commit to version control (already in `.gitignore`)
   - Use strong passwords
   - Rotate credentials regularly

3. **Home Assistant Access**: Ensure Home Assistant has network access to the MCP endpoints:
   - If HA runs in Docker, ensure it's on the same network
   - If HA runs on another machine, adjust `host` in docker-compose

## References

- [Home Assistant MCP Integration](https://www.home-assistant.io/integrations/mcp/)
- [MCP Protocol Documentation](https://github.com/modelcontextprotocol/specification)
- [mcp-proxy Tool](https://github.com/chrishayuk/mcp-proxy)

## Support

For issues or questions:
1. Check container logs: `docker logs <container-name>`
2. Verify Home Assistant logs for MCP errors
3. Review this documentation for troubleshooting steps

