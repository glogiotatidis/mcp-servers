FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY skroutz_server ./skroutz_server/

# Install dependencies
RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd -m -u 1000 skroutz && chown -R skroutz:skroutz /app
USER skroutz

# Create session directory
RUN mkdir -p /home/skroutz/.skroutz-mcp

# Default to stdio mode
CMD ["python", "-m", "skroutz_server"]
