# Sync Tools

API client and sync utilities for the Portable MediaWiki Editor.

## Components

| File | Purpose |
|------|---------|
| `api.py` | MediaWiki API client with login, CSRF, captcha handling |
| `syncer.py` | Push logic with conflict detection |
| `config.py` | Configuration persistence (YAML) |

## API Client Features

- **Two-step login** (required for Fandom/modern MediaWiki)
- **CSRF token** management
- **Interactive captcha** solving via terminal prompts
- **Session persistence** across requests

## Usage

Accessed via root `main.py`:
```bash
uv run main.py clone --url "https://wiki.example.com/api.php"
uv run main.py push
```

## Push Logic

1. Enumerate all pages from local wiki (localhost:8080)
2. For each page, compare revision timestamps with remote  
3. Skip if remote is newer (conflict)
4. Upload changes via `action=edit`
5. Handle captcha if required
