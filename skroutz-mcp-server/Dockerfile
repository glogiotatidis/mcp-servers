FROM python:3.12-slim

WORKDIR /app

# Install Node.js and npm for mcp-proxy
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install mcp-proxy globally
RUN npm install -g @chrishayuk/mcp-proxy

# Copy project files
COPY pyproject.toml ./
COPY skroutz_server ./skroutz_server/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd -m -u 1000 skroutz && chown -R skroutz:skroutz /app
USER skroutz

# Create session directory
RUN mkdir -p /home/skroutz/.skroutz-mcp

# Expose port for mcp-proxy SSE endpoint
EXPOSE 8080

# Default to stdio mode (can be overridden in docker-compose)
CMD ["python", "-m", "skroutz_server"]
