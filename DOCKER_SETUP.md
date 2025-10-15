# Docker Setup Guide

This guide explains how to run the MCP servers using Docker.

## Quick Start

### 1. Create docker-compose.yml from examples

Each MCP server has a `docker-compose.example.yml` file. Copy them to create your own configuration:

```bash
# For Skroutz
cd skroutz-mcp-server
cp docker-compose.example.yml docker-compose.yml

# For E-Fresh
cd ../efresh-mcp-server
cp docker-compose.example.yml docker-compose.yml
```

### 2. Create .env files with credentials

```bash
# Skroutz
cd skroutz-mcp-server
cp .env.example .env
# Edit .env with your Skroutz credentials
echo "SKROUTZ_EMAIL=your@email.com" > .env
echo "SKROUTZ_PASSWORD=your-password" >> .env

# E-Fresh
cd ../efresh-mcp-server
cp .env.example .env
# Edit .env with your E-Fresh credentials
echo "EFRESH_EMAIL=your@email.com" > .env
echo "EFRESH_PASSWORD=your-password" >> .env
```

### 3. Run with Docker Compose

```bash
# Skroutz HTTP server (port 8000)
cd skroutz-mcp-server
docker-compose up skroutz-http

# E-Fresh HTTP server (port 8000)
cd ../efresh-mcp-server
docker-compose up efresh-server
```

## Available Endpoints

### Skroutz MCP Server
- **Root**: http://localhost:8000/
- **Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health
- **SSE**: http://localhost:8000/sse (for Home Assistant)

### E-Fresh MCP Server
- **Root**: http://localhost:8000/
- **Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health
- **SSE**: http://localhost:8000/sse (for Home Assistant)

## Security Notes

✅ **Safe to commit:**
- `docker-compose.example.yml` - Templates
- `.env.example` - Templates

❌ **Never commit:**
- `docker-compose.yml` - Your configuration (in `.gitignore`)
- `.env` - Your credentials (in `.gitignore`)

## Customization

You can modify `docker-compose.yml` (your local copy) to:
- Change ports
- Add volumes
- Configure networks
- Add healthchecks
- Set restart policies

Your changes won't affect the committed templates.

## For Home Assistant

See [HOME_ASSISTANT_SETUP.md](HOME_ASSISTANT_SETUP.md) for detailed instructions on using these servers with Home Assistant's MCP integration.

