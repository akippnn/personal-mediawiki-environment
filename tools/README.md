# Sync Tools

API client and sync utilities for multi-wiki management.

## Components

| File | Purpose |
|------|---------|
| `api.py` | MediaWiki API client (login, CSRF, captcha) |
| `syncer.py` | Batched push with parallel comparison |
| `config.py` | Multi-wiki configuration (wikis.yaml) |
| `wiki_manager.py` | List/swap/create wiki instances |

## Config Structure

Stored in `wikis.yaml`:
```yaml
active_wiki: example_wiki
wikis:
  example_wiki:
    url: https://example.com/api.php
    username: Username
    password: password
    path: wikis/example_wiki
```

## Syncer Optimization

For 10k+ page wikis:
- Batched page enumeration (50 at a time)
- Parallel comparison (4 workers)
- Generator-based to avoid memory issues
