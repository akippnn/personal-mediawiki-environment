# Local MediaWiki Tools

> ⚠️ **Work in Progress** — Further testing needed: rate limits, remote and local sync, conflict resolution, push functionality, and other potential edge cases.

## Quick Start

```bash
uv run main.py clone --url "https://your-wiki.com/api.php" --name mywiki
# Edit at http://localhost:8080 (admin/adminpassword)
uv run main.py push  # untested
```

## Commands

| Command | Description |
|---------|-------------|
| `clone --url URL [--name NAME]` | Clone a wiki |
| `push` | Push local → remote *(untested)* |
| `list` | Show all cloned wikis |
| `swap NAME` | Switch active wiki |
| `status` | Show environment status |
| `start` | Start Docker containers |
| `sync` | Install + import data |
| `cleanup [-v] [-d]` | Stop & remove containers |

## Multi-Wiki Support

```bash
uv run main.py clone --url "https://wiki-a.com/api.php" --name wiki_a
uv run main.py clone --url "https://wiki-b.com/api.php" --name wiki_b
uv run main.py list
uv run main.py swap wiki_a
```

## Project Structure

```
├── main.py          # CLI
├── exporter/        # XML/Markdown exporter
├── tools/           # API client, syncer
└── portable_wiki/   # Docker environment
```

## Requirements

- Python 3.10+ with `uv`
- Docker & Docker Compose

## License

MIT