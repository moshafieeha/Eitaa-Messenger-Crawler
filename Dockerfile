# Eitaa Messenger Crawler Dockerfile
# Multi-stage build for optimized image size and security

# Stage 1: Base Python image - Dependencies
FROM python:3.9-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.4.2

# Create a non-root user to run the application
RUN groupadd -r crawler && useradd -r -g crawler -d /home/crawler -m crawler

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn==20.1.0

# Stage 2: Final image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/data/output/messages \
    BIOS_DIR=/data/output/bios \
    LOGS_DIR=/data/logs \
    META_DIR=/data/meta

# Create a non-root user
RUN groupadd -r crawler && useradd -r -g crawler -d /home/crawler -m crawler

# Set working directory
WORKDIR /app

# Copy dependencies from the base stage
COPY --from=base /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Copy application code and scripts
COPY app/ /app/
COPY scripts/ /scripts/

# Create data directories and set permissions
RUN mkdir -p /data/output/messages /data/output/bios /data/logs /data/meta /config && \
    chown -R crawler:crawler /app /data /scripts /config && \
    chmod +x /scripts/docker-entrypoint.sh

# Switch to non-root user
USER crawler

# Expose health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os; os.access('app/config.py', os.R_OK) or exit(1)"]

# Set the entrypoint script
ENTRYPOINT ["/scripts/docker-entrypoint.sh"]

# Command to run the crawler
CMD ["python", "-m", "app.eita_crawler"]
