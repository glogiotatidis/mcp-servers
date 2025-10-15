# Use Python 3.12 slim image
FROM python:3.12-slim

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

# Expose port for HTTP mode
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "python", "-m", "efresh_server.cli", "--mode", "http", "--host", "0.0.0.0", "--port", "8000"]
