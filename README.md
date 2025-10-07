# MediaWiki Exporter

A robust, resumable tool to export MediaWiki categories into a clean, local format of Markdown files and downloaded media. This tool is designed for archiving, offline viewing, or migrating content.

## Key Features

-   **Resumable Export**: If the script is stopped or crashes, it can be restarted and will automatically resume where it left off by reading an `export_state.json` manifest.
-   **Graceful Shutdown**: Press `Ctrl+C` at any time. The script will finish its current file operation, save its progress, and then exit cleanly.
-   **Structured Output**: Exports content into a logical folder structure (`/pages`, `/templates`, `/media`), making it easy to navigate.
-   **Markdown Conversion**: WikiText is converted to clean Markdown, with YAML frontmatter containing metadata like title and categories.
-   **Rich TUI**: A live-updating Terminal User Interface (TUI) shows real-time stats and logs, built with the `rich` library. A simple fallback is used if `rich` is not installed.
-   **Atomic Writes**: File writes are atomic (write to a temp file, then rename) to prevent file corruption if the script is terminated unexpectedly.

## Installation

This project requires Python 3.7+ and a few package dependencies. Fastest way to install is by using the `uv` package manager.

```bash
# 1. Clone the repository (if you haven't already)
git clone https://github.com/akippnn/mediawiki_exporter.git
cd mediawiki_exporter

uv sync
```

## Usage

The script is run via `main.py` from the command line. You must provide the API URL of the target wiki and the root category you wish to export.

### Basic Command

```bash
uv run main.py --api-url <WIKI_API_URL> --category <CATEGORY_NAME> --output-dir <EXPORT_PATH>
```

### Example

Let's export the "Physics" category from the English Wikipedia into a folder named `./wikipedia_physics_export`.

The API endpoint for English Wikipedia is `https://en.wikipedia.org/w/api.php`.

```bash
uv run main.py \
    --api-url https://en.wikipedia.org/w/api.php \
    --category "Physics" \
    --output-dir ./wikipedia_physics_export
```

Once you run the command, the TUI will appear and the export process will begin.

### Command-Line Arguments

| Argument         | Required | Default         | Description                                                              |
| ---------------- | -------- | --------------- | ------------------------------------------------------------------------ |
| `--api-url`      | **Yes**  | N/A             | The URL of the MediaWiki `api.php` endpoint.                             |
| `--category`     | **Yes**  | N/A             | The name of the root category to start the export from.                  |
| `--output-dir`   | No       | `./export`      | The local directory where files will be saved.                           |
| `--sleep`        | No       | `0.5`           | Seconds to sleep between API requests to be polite to the server.        |
| `--maxlag`       | No       | `5`             | The `maxlag` parameter sent to the API to pause on high server load.     |
| `--user-agent`   | No       | `mediawiki-exporter/2.0` | The User-Agent string to use for API requests.                   |

## Project Structure

The codebase is organized with a clear separation of concerns to make it easy to maintain and extend.

```
.
├── main.py                     # Entrypoint: Parses args, starts the TUI
├── README.md                   # This file
├── requirements.txt            # Project dependencies
└── mediawiki_exporter/
    ├── __init__.py
    ├── api.py                  # Handles all network requests to the MediaWiki API
    ├── exporter.py             # Contains the core crawling and file processing logic
    ├── state.py                # Manages loading and saving the export state for resuming
    ├── tui.py                  # The Rich-based Terminal User Interface
    └── utils.py                # Helper functions (e.g., atomic writes, sanitize filename)
```

## License

This project is licensed under the MIT License.