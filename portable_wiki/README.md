# Portable Wiki

Docker-based local MediaWiki environment.

## Quick Start

```bash
cd portable_wiki
python manager.py start
python manager.py install
python manager.py import
```

Access at http://localhost:8080 (admin/adminpassword)

## Manager Commands

| Command | Description |
|---------|-------------|
| `start` | Start containers |
| `stop` | Stop containers |
| `status` | Show container status |
| `install` | Run MediaWiki install |
| `import` | Import XML dumps (parallel) |
| `extensions --list` | List installed extensions |

## Docker Architecture

Uses entrypoint pattern for fast startup:

1. **setup** — Alpine container installs extensions
2. **database** — MariaDB with health checks
3. **mediawiki** — Waits for setup completion

## Data Layout

```
portable_wiki/
├── data/              # Symlink to active wiki's data
│   ├── xml/           # XML dumps
│   └── media/         # Images
├── docker-compose.yml
├── manager.py         # Standalone manager
└── mediawiki-entrypoint.sh
```
