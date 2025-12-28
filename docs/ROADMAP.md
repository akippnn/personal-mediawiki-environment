# Roadmap

## Backlog

### Sync Robustness
- [ ] **Diff Comparison**: Implement content diff in `tools/syncer.py`
- [ ] **Conflict Markers**: Create `.conflict` files with both versions
- [ ] **Force Push**: Add `--force` flag to overwrite remote

### Push Performance
- [ ] **Parallel API Edits**: Use `ThreadPoolExecutor` for concurrent page pushes (4-8x speedup)
  - Note: MediaWiki API has no bulk edit endpoint; each page requires separate `action=edit`
  - Rate limiting still applies (`maxlag`, throttling)

### Offline Commits
- [ ] **Local History**: Store revision diffs in SQLite or JSON files
- [ ] **Replay**: `push` replays stored diffs instead of full state sync

### Media Push
- [ ] **Image Upload**: Hash local images (SHA1), compare with remote via `aiprop=sha1`
- [ ] **Batch Upload**: Use `action=upload` with limit-batching
