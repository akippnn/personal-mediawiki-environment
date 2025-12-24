# Portable MediaWiki Editor

Clone, edit, and sync MediaWiki sites locally. Work offline, then push your changes back upstream.

## Features

- **Clone**: Download an entire wiki (pages, images, extensions)
- **Edit**: Run a full MediaWiki locally (Docker-based)
- **Push**: Sync changes back with conflict detection & captcha handling

## Quick Start

```bash
uv sync
uv run main.py clone --url "https://your-wiki.com/api.php"
# Edit at http://localhost:8080 (admin/adminpassword)
uv run main.py push
```

## Commands

| Command | Description |
|---------|-------------|
| `clone` | Clone remote wiki → local |
| `push`  | Push local → remote wiki |
| `start` | Start Docker containers |
| `setup` | Import data into wiki |
| `cleanup` | Stop & remove containers |
| `export`| Run standalone exporter |

## Project Structure

```
├── main.py          # Orchestrator CLI
├── exporter/        # Standalone XML/Markdown exporter
├── tools/           # API client & sync logic
└── portable_wiki/   # Docker-based local MediaWiki
```

## Requirements

- Python 3.7+
- Docker & Docker Compose
- `uv` package manager

## License

MIT