#!/bin/bash
# Start MCP proxy servers for Home Assistant integration

set -e

# Check if mcp-proxy is installed
if ! command -v mcp-proxy &> /dev/null; then
    echo "❌ mcp-proxy not found!"
    echo "Installing mcp-proxy..."
    npm install -g @chrishayuk/mcp-proxy
fi

# Check for .env files
if [ ! -f "../skroutz-mcp-server/.env" ]; then
    echo "⚠️  No .env file found for Skroutz"
    echo "Create skroutz-mcp-server/.env with:"
    echo "  SKROUTZ_EMAIL=your@email.com"
    echo "  SKROUTZ_PASSWORD=your-password"
    exit 1
fi

if [ ! -f "../efresh-mcp-server/.env" ]; then
    echo "⚠️  No .env file found for E-Fresh"
    echo "Create efresh-mcp-server/.env with:"
    echo "  EFRESH_EMAIL=your@email.com"
    echo "  EFRESH_PASSWORD=your-password"
    exit 1
fi

# Load environment variables
export $(cat ../skroutz-mcp-server/.env | xargs)
export $(cat ../efresh-mcp-server/.env | xargs)

echo "🚀 Starting MCP Proxy servers for Home Assistant..."
echo ""
echo "Skroutz SSE endpoint: http://localhost:8080/sse"
echo "E-Fresh SSE endpoint: http://localhost:8081/sse"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Start both proxies in background
cd ../skroutz-mcp-server
mcp-proxy --stdio "python -m skroutz_server" --port 8080 --host 0.0.0.0 &
SKROUTZ_PID=$!

cd ../efresh-mcp-server
mcp-proxy --stdio "python -m efresh_server" --port 8081 --host 0.0.0.0 &
EFRESH_PID=$!

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Stopping MCP proxy servers..."
    kill $SKROUTZ_PID 2>/dev/null || true
    kill $EFRESH_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for both processes
wait

