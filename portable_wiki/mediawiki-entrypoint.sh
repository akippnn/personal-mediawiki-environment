#!/bin/sh
# MediaWiki Setup Entrypoint
# Runs before MediaWiki container starts
# Installs extensions and prepares the environment

set -e

echo "=== MediaWiki Setup Entrypoint ==="

# Known extensions to install (from Gerrit)
EXTENSIONS="Scribunto ParserFunctions TemplateStyles Cite WikiEditor CodeEditor InputBox CategoryTree Gadgets PageImages TextExtracts Poem"

install_extension() {
    name="$1"
    dest="/extensions/$name"
    
    if [ -d "$dest" ]; then
        echo "  ✓ $name (cached)"
        return 0
    fi
    
    echo "  Installing $name..."
    for branch in REL1_45 REL1_44 REL1_43 master; do
        if git clone --depth 1 --branch "$branch" \
            "https://gerrit.wikimedia.org/r/mediawiki/extensions/$name" \
            "$dest" 2>/dev/null; then
            echo "  ✓ $name"
            return 0
        fi
    done
    echo "  ✗ $name (failed)"
    return 1
}

# Install extensions in parallel (max 4 jobs)
echo ""
echo "[1/2] Installing Extensions..."
apk add --no-cache git > /dev/null 2>&1

for ext in $EXTENSIONS; do
    install_extension "$ext" &
    
    # Limit parallel jobs
    while [ $(jobs -r | wc -l) -ge 4 ]; do
        sleep 0.5
    done
done
wait

echo ""
echo "[2/2] Preparing XML imports..."
if [ -d "/data/xml" ]; then
    xml_count=$(ls -1 /data/xml/*.xml 2>/dev/null | wc -l)
    echo "  Found $xml_count XML files ready for import"
else
    echo "  No XML data found"
fi

echo ""
echo "=== Setup Complete ==="
