# MediaWiki Exporter

Standalone tool to export MediaWiki content to XML or Markdown format.

## Features

- **XML Export**: Native MediaWiki dumps for importing into another instance
- **Markdown Export**: Convert wikitext to Markdown for static sites  
- **Incremental Updates**: Tracks revision IDs to skip unchanged pages
- **Image Download**: Fetches all images from the wiki
- **Extension Detection**: Lists installed extensions
- **All Namespaces**: Exports Main, Talk, Template, Category, Module, etc.

## Usage

### Via Root CLI (Recommended)
```bash
uv run main.py export -- --api-url "https://wiki.example.com/api.php" --scope all --format xml
```

### Standalone
```bash
cd exporter
uv run main.py --api-url "https://wiki.example.com/api.php" --scope all --format xml
```

## Options

| Option | Description |
|--------|-------------|
| `--api-url` | **Required**. MediaWiki API endpoint |
| `--scope` | `category` or `all` (default: category) |
| `--category` | Root category (required if scope=category) |
| `--format` | `markdown` or `xml` (default: markdown) |
| `--output-dir` | Destination folder (default: ./export) |
| `--no-tui` | Disable TUI, use console logging |

## Output Structure

```
export/
├── xml/                # XML dumps (batched)
├── pages/              # Markdown files (if format=markdown)
├── media/              # Downloaded images
├── templates/          # Template markdown files  
├── extensions.yaml     # Detected extensions
└── export_state.json   # Revision tracking for incremental updates
```