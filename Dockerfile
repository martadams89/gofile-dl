FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies without specific versions to avoid compatibility issues
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group with explicit IDs
RUN groupadd -r -g 1000 appuser && useradd -r -g appuser -u 1000 appuser

# Create necessary directories with proper permissions
RUN mkdir -p /app /data && chown -R appuser:appuser /app /data

# Install Python dependencies
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Set environment variables
ENV PORT=2355 \
    HOST="0.0.0.0" \
    BASE_DIR="/data" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE $PORT

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["python", "app.py"]
