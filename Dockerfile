FROM python:3.13-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add these lines before installing Python dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY --chown=gofile:gofile requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=gofile:gofile . .

# Set environment variables
ENV PORT=2355 \
    HOST="0.0.0.0" \
    BASE_DIR="/data" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create a directory for the downloads
RUN mkdir -p /data && chown -R gofile:gofile /data

# Expose port
EXPOSE $PORT

# Switch to non-root user
USER gofile

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["python", "app.py"]
