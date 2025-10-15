# Use Python 3.12 slim image
FROM python:3.12-slim

# Install Node.js and npm for mcp-proxy
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install mcp-proxy globally
RUN npm install -g @chrishayuk/mcp-proxy

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY efresh_server ./efresh_server

# Expose port for mcp-proxy SSE endpoint
EXPOSE 8081

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command runs mcp-proxy wrapping the stdio MCP server
CMD ["mcp-proxy", "--stdio", "uv run python -m efresh_server", "--port", "8081", "--host", "0.0.0.0"]
