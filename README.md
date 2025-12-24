# Portable MediaWiki Editor

Clone, edit, and sync MediaWiki sites locally. Work offline, then push changes back.

## Quick Start

```bash
uv run main.py clone --url "https://your-wiki.com/api.php" --name mywiki
# Edit at http://localhost:8080 (admin/adminpassword)
uv run main.py push
```

## Commands

| Command | Description |
|---------|-------------|
| `clone --url URL [--name NAME]` | Clone a wiki |
| `push` | Push local → remote |
| `list` | Show all cloned wikis |
| `swap NAME` | Switch active wiki |
| `start` | Start Docker containers |
| `setup` | Import data into wiki |
| `cleanup [-v] [-d]` | Stop & remove containers |

## Multi-Wiki Support

Clone multiple wikis and switch between them:
```bash
uv run main.py clone --url "https://wiki-a.com/api.php" --name wiki_a
uv run main.py clone --url "https://wiki-b.com/api.php" --name wiki_b
uv run main.py list
uv run main.py swap wiki_a
```

## Project Structure

```
├── main.py          # Orchestrator CLI
├── exporter/        # XML/Markdown exporter
├── tools/           # API client, syncer, config
└── portable_wiki/   # Docker-based local MediaWiki
    └── manager.py   # Standalone instance manager
```

## Requirements

- Python 3.7+ with `uv`
- Docker & Docker Compose

## License

MIT