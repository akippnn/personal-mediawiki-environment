# Roadmap

## ✅ Implemented

### Core Infrastructure
- [x] **Unified CLI** (`pme`): Single entry point with subcommands
- [x] **Multi-Wiki Support**: `wikis.yaml` config, `clone`, `list`, `swap` commands
- [x] **Docker Environment**: `docker-compose` with version-matched MediaWiki image

### Export
- [x] **XML Export**: Full wiki export via `action=query&export`
- [x] **Revision History**: `--with-history` flag for full revision export
- [x] **Siteinfo Detection**: Queries `meta=siteinfo` for version + extensions
- [x] **Parallel Image Downloads**: 4 workers with SHA1 caching

### Extension Management
- [x] **Auto-Detection**: Extracts extension list from remote wiki
- [x] **Version-Aware Cloning**: Clones `REL1_XX` branch matching wiki version
- [x] **Gerrit Fallback**: Tries Gerrit for archived/unknown extensions

### Sync Engine
- [x] **Fetch/Pull**: Staging area (`.tmp/`) with conflict detection
- [x] **Local Change Detection**: Tracks `local_revid` vs `base_revid`
- [x] **Push**: Uploads text pages via `action=edit`

---

## 🔶 TODO

### 🧪 Needs Testing / Validation

- [ ] **Rate Limiting**: Verify `maxlag` and backoff logic during heavy syncs.
- [ ] **Full Sync Cycle**: Test `clone` → `local edit` → `push` → `fetch` loop robustness.
- [ ] **Conflict Resolution**: Validate how the system behaves when both local and remote change (currently basic file flagging).
- [ ] **Push Edge Cases**: Test pushing pages with special characters, large content, or protected status.

---

## 🔷 Planned

### Architecture Improvements
- [ ] **SQLite Backend**: Migrate from MariaDB to SQLite for the portable wiki.
  - Reduces writes and container overhead.
  - Enables "Database Swapping" via simple file moves in `wikis/{name}/`.
- [ ] **Nuitka Compilation**: Compile `main.py` and dependencies into a standalone binary for easier distribution and performance.

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
- [ ] **Parallel Uploads**: Use `ThreadPoolExecutor` for concurrent `action=upload` calls (no batch API exists)