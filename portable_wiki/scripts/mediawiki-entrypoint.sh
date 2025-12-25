#!/bin/sh
# MediaWiki Setup Entrypoint
# Runs before MediaWiki container - now only handles setup signaling
# Extensions are installed by Python during clone/pull

set -e

echo "=== MediaWiki Setup Entrypoint ==="

# Check if extensions were pre-installed
if [ -d "/extensions" ] && [ "$(ls -A /extensions 2>/dev/null)" ]; then
    ext_count=$(ls -1 /extensions | wc -l | tr -d ' ')
    echo "✓ Found $ext_count pre-installed extensions"
else
    echo "⚠ No extensions pre-installed"
fi

# Check for data
if [ -d "/data/xml" ]; then
    xml_count=$(ls -1 /data/xml/*.xml 2>/dev/null | wc -l | tr -d ' ')
    echo "✓ Found $xml_count XML files ready for import"
else
    echo "⚠ No XML data found"
fi

echo ""
echo "=== Setup Complete ==="
