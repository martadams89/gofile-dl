# gofile-dl

Forked from [rkwyu/gofile-dl](https://github.com/rkwyu/gofile-dl) by martadams89.  
A CLI tool to download files from a gofile.io link – now with a modern, responsive web interface featuring light/dark mode, enhanced task tracking with overall progress/ETA, friendly naming, filtering, cancellation, deletion of downloaded files, and Docker support.

## About

gofile-dl is a tool to download directories and files from a gofile.io URL. This fork adds:

- A Flask web interface that includes:
  - A form to enter a GoFile URL, optional password, and select a download directory.
  - A dynamic file system browser.
  - Task tracking with progress bars for individual files and overall folder progress with an estimated time of arrival (ETA).
  - Friendly task naming (updated as files are downloaded).
  - Controls to pause (stub), cancel, delete (remove files from disk), and manually remove tasks from the panel.
  - A filter to show tasks older than 1, 7, 30, 180, or 365 days.
  - A dark/light mode toggle.
- Docker and Docker Compose support for easy deployment.

## Setup

1. Clone the repository:

```console
git clone https://github.com/martadams89/gofile-dl
```

2. Install dependencies:

```console
cd ./gofile-dl
python -m pip install -r requirements.txt
```

## CLI Usage

```console
usage: run.py [-h] [-d DIR] [-p PASSWORD] url
```

Default output directory is `./output`.

#### Example (CLI):

```console
python run.py https://gofile.io/d/foobar
```

## Web Interface

The Flask web interface includes:

- A form to input a GoFile URL, optional password, and a browsable download directory.
- A task panel that displays:
  - Real-time progress bars (individual file progress and overall folder progress with ETA).
  - Friendly names (automatically updated from the downloaded folder name if available).
  - Timestamps for when tasks started.
  - Controls to pause (stub), cancel, delete the downloaded files from disk (with confirmation), and manually remove tasks.
  - A dropdown filter to show tasks older than a specified number of days.
- A dark/light mode toggle.

### To run the web interface:

```console
python app.py
```

Access the app at [http://localhost:2355](http://localhost:2355) or on the port set via the `PORT` environment variable.

## Docker

A Dockerfile and docker-compose.yml are included.

### Build and Run with Docker:

```console
docker build -t gofile-dl .
docker run -p 2355:2355 gofile-dl
```

### Using Docker Compose:

```console
docker-compose up --build
```

This Compose file uses the image `martadams89/gofile-dl:latest`.

## Environment Variables

- `PORT`: Set the port the web interface runs on (default 2355).
- `BASE_DIR`: Set the base directory for file browsing (default is `/app` when using the web interface).

## New Features

- **Overall Progress & ETA:** For folder downloads, overall progress is computed and an ETA is displayed.
- **File Deletion:** A delete button is available for each task to remove the downloaded files from disk (with a confirmation prompt).
- **Task Management:** Cancel and manual removal (delete from task list) functionalities have been added.

## License

This project is licensed under the [MIT License](LICENSE.md)
