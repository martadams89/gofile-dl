# GoFile Downloader (gofile-dl)

**Note: This project began as a fork of [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl) but has since evolved into a completely rebuilt application with a different architecture and extensive new features.**

![Version](https://img.shields.io/badge/version-1.4.0-blue)
![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

A powerful, modern web application and CLI tool for downloading files and folders from GoFile.io links. Featuring a responsive web interface, task management, progress tracking, and Docker support.

_Originally inspired by [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl) but completely rebuilt with extensive enhancements and a modern architecture._

## Important Notes

### GoFile API Compatibility (January 2026)

This application has been updated to work with GoFile's latest API changes:

- ✅ **Updated Authentication**: Uses `X-Website-Token` header for API access
- ✅ **Nested Folders**: Full support for deeply nested folder structures with UUID-based IDs
- ✅ **Special Characters**: Properly handles emoji and special characters in folder names
- ✅ **Password Protection**: Supports SHA-256 password hashing for protected content
- ✅ **Recursive Downloads**: Automatically traverses and downloads all subfolders

**Note**: The GoFile API structure changed in early 2026. This version includes all necessary updates to maintain compatibility.

## Features

### Core Functionality

- Download individual files or entire folder structures from GoFile.io links
- **Full recursive support** for nested subfolders (including UUID-based and short-form IDs)
- **Password-protected content** with SHA-256 hash authentication
- **Smart folder handling** with automatic emoji and special character sanitization
- CLI and web interface options
- Automatic retry on failed downloads with configurable attempts

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
- **Emoji stripping option** for Linux CLI compatibility (removes emojis from folder/file names)
- **Incremental/Sync mode** - Only download new files, skip existing ones
  - Perfect for ongoing series with "NEW FILES in" folders
  - Automatically handles folder renames (e.g., "⭐NEW FILES in Show S1" → "Show S1")
  - Tracks downloaded files to avoid re-downloading
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
      - ./config:/config
    environment:
      - PORT=2355
      - HOST=0.0.0.0
      - BASE_DIR=/data
      - CONFIG_DIR=/config
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
| `CONFIG_DIR`      | Directory for config/tracking  | `/config`                 | `/app/config`     |
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
- `/config`: Persistent storage for download tracking files (incremental mode)

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
      - ./config:/config
    environment:
      - AUTH_ENABLED=true
      - AUTH_USERNAME=admin
      - AUTH_PASSWORD=secure-password
      - CONFIG_DIR=/config
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
      - ./config:/config
    environment:
      - PORT=2355
      - CONFIG_DIR=/config
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
   - **Permission denied errors**: Ensure the mounted directory is writable by UID 1000 (default container user)

4. **Authentication issues**
   - Ensure AUTH_ENABLED is set to "true" (case-sensitive)
   - Verify username and password are correctly set
   - Clear browser cache and cookies

5. **GoFile download errors**
   - Error "Cannot get wt": GoFile may have updated their JavaScript structure. Check for application updates.
   - Error "API error: error-notPremium": Ensure you're using the latest version with `X-Website-Token` header support
   - Nested folders not downloading: Verify you're providing the top-level folder URL, not individual file links
   - Special characters in filenames: These are automatically sanitized - check the `downloads` folder for the converted names

## Testing

### Running Tests

A test script is provided to verify GoFile connectivity:

```bash
# Test with environment variables
export GOFILE_TEST_URL="https://gofile.io/d/YOUR_CONTENT_ID"
export GOFILE_TEST_PASSWORD="your_password"  # Optional, only if content is password-protected
python test_gofile_api.py

# Or test directly with arguments
python test_gofile_api.py --url "https://gofile.io/d/YOUR_CONTENT_ID" --password "your_password"
```

The test script verifies:

- Token acquisition from GoFile API
- WebsiteToken (wt) extraction from config.js
- Content access with proper authentication
- Nested folder structure retrieval

## Use Case: Tracking Ongoing Series with Incremental Mode

The incremental/sync mode is perfect for content that updates regularly, such as TV series, podcast archives, or any collection that receives periodic updates.

### Why Use Incremental Mode?

When downloading from ongoing series or regularly updated folders:

- Avoid re-downloading files you already have
- Save bandwidth and time
- Keep your local copy synchronized with the remote folder
- Handle folder renames automatically (common with "NEW FILES" prefixes)

### How It Works

1. **Initial Download**: Download the entire folder structure
   - Enable "Incremental/Sync mode" checkbox in the web UI
   - Or use `incremental=true` via API/curl

2. **Subsequent Updates**: Run the same download again
   - Only NEW files are downloaded
   - Previously downloaded files are automatically skipped
   - Handles folder renames with customizable pattern matching
   - Default patterns strip: `⭐NEW FILES in`, `NEW FILES in`, `⭐`

3. **Behind the Scenes**:
   - Creates persistent tracking file: `.gofile_tracker_<contentId>.json` in `/config`
   - Stores list of downloaded file IDs and names
   - Matches folders even when renamed using pattern normalization
   - Logs all skipped files for visibility

### Customizing Folder Patterns

Different uploaders use different naming conventions. You can customize the patterns to match your specific use case:

1. **Via Web UI**:
   - Click "Advanced Options" to reveal pattern configuration
   - Enter pipe-separated patterns: `⭐NEW FILES in |NEW FILES in |⭐`

2. **Via API/curl**:

   ```bash
   curl -X POST http://localhost:2355/start \
     -d "url=https://gofile.io/d/abc123" \
     -d "incremental=true" \
     -d "folder_pattern=UPDATED |⭐NEW |*NEW FILES in "
   ```

3. **Pattern Examples**:
   - `⭐NEW FILES in |NEW FILES in |⭐` (default) matches:
     - `⭐NEW FILES in Show S1 [10]` → `Show S1 [10]`
     - `NEW FILES in Episode Pack` → `Episode Pack`
   - `UPDATED |⭐NEW |*NEW FILES in ` matches:
     - `UPDATED Show S1` → `Show S1`
     - `⭐NEW Episode Pack` → `Episode Pack`
     - `*NEW FILES in Series` → `Series`

### Example Workflow

```bash
# Week 1: Initial download - gets everything
docker-compose exec gofile-dl curl -X POST http://localhost:2355/start \
  -d "url=https://gofile.io/d/abc123" \
  -d "incremental=true" \
  -d "folder_pattern=⭐NEW FILES in |NEW FILES in |⭐"

# Week 2: Update download - only new episodes
# Same command - automatically skips existing files!
docker-compose exec gofile-dl curl -X POST http://localhost:2355/start \
  -d "url=https://gofile.io/d/abc123" \
  -d "incremental=true" \
  -d "folder_pattern=⭐NEW FILES in |NEW FILES in |⭐"
```

### Important Notes

- Tracking files are stored in `/config` directory - **ensure this volume is mounted** in your docker-compose.yml
- Delete the tracking file `.gofile_tracker_<contentId>.json` to force a complete re-download
- The tracking is per content ID, so different GoFile folders are tracked separately
- Progress shown in the UI is per-subfolder, allowing you to see which folder is currently being processed

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
