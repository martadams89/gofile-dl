# GoFile Downloader (gofile-dl)

**Note: This project began as a fork of [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl) but has since evolved into a completely rebuilt application with a different architecture and extensive new features.**

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A powerful, modern web application and CLI tool for downloading files and folders from GoFile.io links. Featuring a responsive web interface, task management, progress tracking, and Docker support.

_Originally inspired by [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl) but completely rebuilt with extensive enhancements and a modern architecture._

## Features

### Core Functionality

- Download individual files or entire folder structures from GoFile.io links
- Support for password-protected content
- CLI and web interface options
- Automatic retry on failed downloads

### Web Interface

- Modern, responsive design with Bootstrap 5
- Light/dark mode toggle with preference saving
- Interactive file system browser for selecting download locations
- Real-time download progress tracking with overall progress and ETA
- Task categorization and filtering by status and date
- Comprehensive dashboard with download statistics

### Advanced Features

- Download speed limiting/throttling
- Configurable retry attempts for failed downloads
- Pause/resume downloads
- File size information display
- Task management (cancel, delete files, remove from list)
- Copy download links to clipboard
- Authentication for security

### Deployment

- Docker and Docker Compose support
- Environment variable configuration
- Health check endpoint for container monitoring
- CSRF protection and security best practices

## Quick Start

### Using Docker (Recommended)

## Docker Deployment Guide

GoFile Downloader is designed to run well in containers. This section provides comprehensive information on deploying with Docker.

### Quick Start with Docker

```bash
# Build the Docker image
docker build -t gofile-dl:latest .

# Run with basic configuration
docker run -d --name gofile-dl \
  -p 2355:2355 \
  -v /your/download/path:/data \
  gofile-dl:latest
```

### Docker Compose Deployment

Create a `docker-compose.yml` file:

```yaml
version: "3.8"

services:
  gofile-dl:
    image: ghcr.io/martadams89/gofile-dl:latest
    container_name: gofile-dl
    ports:
      - "2355:2355"
    volumes:
      - ./downloads:/data
    environment:
      - PORT=2355
      - HOST=0.0.0.0
      - BASE_DIR=/data
      - SECRET_KEY=change-this-to-a-random-string-in-production
      # Uncomment to enable authentication
      # - AUTH_ENABLED=true
      # - AUTH_USERNAME=admin
      # - AUTH_PASSWORD=your-secure-password
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:2355/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
```

Run with:

```bash
docker-compose up -d
```

### Environment Variables Reference

| Variable          | Description                    | Default                   | Example           |
| ----------------- | ------------------------------ | ------------------------- | ----------------- |
| `PORT`            | Web server port                | `2355`                    | `8080`            |
| `HOST`            | Web server host                | `0.0.0.0`                 | `127.0.0.1`       |
| `BASE_DIR`        | Base directory for downloads   | `/app`                    | `/downloads`      |
| `SECRET_KEY`      | Flask secret key for sessions  | Random value              | `my-secret-key`   |
| `DEBUG`           | Enable Flask debug mode        | `false`                   | `true`            |
| `AUTH_ENABLED`    | Enable basic authentication    | `false`                   | `true`            |
| `AUTH_USERNAME`   | Authentication username        | `admin`                   | `user`            |
| `AUTH_PASSWORD`   | Authentication password        | `change-me-in-production` | `secure-password` |
| `DEFAULT_RETRIES` | Default retry attempts         | `3`                       | `5`               |
| `RETRY_DELAY`     | Seconds between retry attempts | `5`                       | `10`              |

### Docker Volumes

GoFile Downloader uses the following volumes:

- `/data`: Main storage location for downloaded files

### Security Best Practices

For a secure deployment:

1. **Use Authentication**: Enable authentication by setting `AUTH_ENABLED=true` and setting a strong password
2. **Set a Custom Secret Key**: Provide a strong `SECRET_KEY` for sessions and CSRF protection
3. **Limit Network Access**: Consider running behind a reverse proxy with HTTPS
4. **Use Non-Root User**: The container already runs as non-root user `gofile`
5. **Keep Updated**: Regularly rebuild the container to get security updates

### Advanced Docker Configurations

#### With HTTPS Reverse Proxy (Traefik Example)

```yaml
version: "3.8"

services:
  gofile-dl:
    image: ghcr.io/martadams89/gofile-dl:latest
    volumes:
      - ./downloads:/data
    environment:
      - AUTH_ENABLED=true
      - AUTH_USERNAME=admin
      - AUTH_PASSWORD=secure-password
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.gofile.rule=Host(`gofile.example.com`)"
      - "traefik.http.routers.gofile.entrypoints=websecure"
      - "traefik.http.routers.gofile.tls.certresolver=letsencrypt"
    networks:
      - proxy
    restart: unless-stopped

networks:
  proxy:
    external: true
```

#### Resource-Limited Configuration

```yaml
version: "3.8"

services:
  gofile-dl:
    image: ghcr.io/martadams89/gofile-dl:latest
    volumes:
      - ./downloads:/data
    environment:
      - PORT=2355
    deploy:
      resources:
        limits:
          cpus: "0.50"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
    restart: unless-stopped
```

### Health Check and Monitoring

GoFile Downloader provides a health check endpoint at `/health` that returns system information and application status in JSON format. This can be used by container orchestration tools to monitor the application's health.

Example health check response:

```json
{
  "status": "ok",
  "timestamp": 1651234567.89,
  "system": {
    "system": "Linux",
    "python_version": "3.11.0",
    "cpu_usage": 5.2,
    "memory": {
      "total": 8589934592,
      "available": 4294967296,
      "percent": 50.0
    },
    "disk": {
      "total": 107374182400,
      "free": 53687091200,
      "percent": 50.0
    }
  },
  "application": {
    "status": "healthy",
    "active_tasks": 2,
    "version": "2.0.0"
  }
}
```

### Troubleshooting Docker Deployment

1. **Container fails to start**

   - Check logs: `docker logs gofile-dl`
   - Verify environment variables are correctly set
   - Ensure the download directory has correct permissions

2. **Cannot access web interface**

   - Confirm port mapping: `docker ps`
   - Check if the host firewall allows access to the port
   - Verify the container is running: `docker ps | grep gofile-dl`

3. **Download files not appearing**

   - Check the volume mounting: `docker inspect gofile-dl`
   - Verify the BASE_DIR environment variable is set correctly
   - Check directory permissions

4. **Authentication issues**
   - Ensure AUTH_ENABLED is set to "true" (case-sensitive)
   - Verify username and password are correctly set
   - Clear browser cache and cookies

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Here's how you can help:

1. **Report bugs**: Open an issue describing the bug and how to reproduce it
2. **Suggest features**: Open an issue describing the feature and its benefits
3. **Submit pull requests**: Fork the repository and submit a PR with your changes

Please ensure your code follows existing style conventions and includes appropriate tests.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/gofile-dl.git
cd gofile-dl

# Install dependencies for development
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Lint your code
flake8 .
black .
```

## Support

Having issues with gofile-dl? Here are some resources:

- **GitHub Issues**: Use our [issue tracker](https://github.com/martadams89/gofile-dl/issues) for bug reports and feature requests.

## Versioning

We use [SemVer](https://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/martadams89/gofile-dl/tags).

## Acknowledgements

- Original concept by [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl).
- Built with [Flask](https://flask.palletsprojects.com/) and [Bootstrap](https://getbootstrap.com/).
- Icons from [Bootstrap Icons](https://icons.getbootstrap.com/).
- Thanks to all contributors who have helped this project evolve!
