# Local MediaWiki Tools

Clone MediaWiki sites locally, edit offline, push changes back.

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
| `setup` | Install + import data |
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