# Personal Mediawiki Environment

> ⚠️ **Work in Progress** — Further testing needed: rate limits, remote and local sync, conflict resolution, push functionality, and other potential edge cases. Do not use in production. See [ROADMAP.md](./docs/ROADMAP.md) for more details.

This toolset allows you to create a local Mediawiki environment, clone a remote wiki, and manage it locally. It is currently in development and is not yet ready for production use.

## Why This Tool?

This is an alternative to established tools like [Extension:PageSync](https://www.mediawiki.org/wiki/Extension:PageSync) (mature, SMWCon-featured) and [Git-Mediawiki](https://github.com/Git-Mediawiki/Git-Mediawiki) (decade of development, git community backed).

| Feature | PageSync Extension | git-remote-mediawiki | This Tool (API-Based) |
|---------|-------------------|---------------------|----------------------|
| Primary User | System Administrators | Developers / Coders | Wiki Architects / Power Users |
| Requirements | Server Root + SSH access | Git + Perl (Strawberry Perl for Windows) | Docker |
| Logic (Lua/Templates) | Raw Transfer: Moves files between server directories. | Git Managed: Edit locally, push as text commits. | Live Sandbox: Local edit + instant preview in local MW. |
| Media Support | Full: Built-in sync for File: namespace. | Partial: Experimental; requires Git-LFS for stability. | Clone Only: Pulls media (Push currently WIP). |
| Access Required | SSH/File System: Must install extension on server. | API/Git: Remote access via API. | API Only: No server-side installation required. |
| Environment Sync | Artifacts Only: Templates, Files, Modules. | History Only: Pages and revisions only. | Full Clone: Replicates content/logic into a local MW. |
| Conflict Handling | Mature: Version tracking via index files. | Git-Native: Uses merge/rebase logic. | WIP: Potential for API-based diff checking. |
| Maturity | ★★★★★ (Stable) | ★★★★☆ (Stable but niche) | ★☆☆☆☆ (Experimental) |

**What this tool does differently:** Instead of syncing wikitext files, it runs a **complete local MediaWiki instance** where templates and Scribunto modules render natively.

**The honest trade-off:** PageSync and Git-MW have years of battle-tested edge-case handling. This tool's sync/push logic is weeks away from that level of reliability. Use this if you need a true local wiki preview; use the established tools if you need production-grade sync.

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