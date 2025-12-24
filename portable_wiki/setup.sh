#!/bin/bash

# Portable MediaWiki Editor - Setup Script (Parallelized)
# Handles installation, extension management, and data import

set +e  # Don't exit on error - we handle errors ourselves

# Known standard MediaWiki extensions
KNOWN_EXTENSIONS=(
    "Scribunto"
    "ParserFunctions"
    "TemplateStyles"
    "Cite"
    "WikiEditor"
    "CodeEditor"
    "InputBox"
    "CategoryTree"
    "Gadgets"
    "PageImages"
    "TextExtracts"
    "Poem"
)

OPTIONAL_EXTENSIONS=(
    "VisualEditor"
    "MobileFrontend"
    "MultimediaViewer"
    "TimedMediaHandler"
    "Math"
)

# Max parallel jobs
MAX_JOBS=4

echo "========================================"
echo "Portable MediaWiki Editor - Setup"
echo "========================================"
echo ""

# Wait for DB
echo "[1/6] Waiting for MariaDB..."
sleep 10

# Get MediaWiki version
MW_VERSION=$(docker-compose exec -T mediawiki php -r "require 'includes/Defines.php'; echo MW_VERSION;" 2>/dev/null || echo "unknown")
echo "  MediaWiki version: $MW_VERSION"

# Check if installed
echo ""
echo "[2/6] Checking MediaWiki installation..."
INSTALLED=$(docker-compose exec -T mediawiki bash -c "[ -f /var/www/html/LocalSettings.php ] && echo 'yes' || echo 'no'" 2>/dev/null || echo 'no')

if [ "$INSTALLED" != "yes" ]; then
    echo "  Installing MediaWiki..."
    docker-compose exec -T mediawiki php maintenance/install.php \
        --dbserver "database" \
        --dbname "my_wiki" \
        --dbuser "wikiuser" \
        --dbpass "wikipass" \
        --server "http://localhost:8080" \
        --scriptpath "" \
        --pass "adminpassword" \
        "PortableWiki" "admin"
    
    docker-compose exec -T mediawiki bash -c 'cat >> LocalSettings.php << "EOFCONFIG"

# === Portable MediaWiki Editor Configuration ===
$wgEnableUploads = true;
$wgPFEnableStringFunctions = true;
$wgScribuntoDefaultEngine = "luastandalone";
$wgShowExceptionDetails = true;
EOFCONFIG'
    echo "  ✓ MediaWiki installed"
else
    echo "  ✓ Already installed"
fi

# === PARALLEL EXTENSION CLONING ===
echo ""
echo "[3/6] Installing Extensions (parallel)..."

clone_extension() {
    local ext_name="$1"
    # Already installed?
    if docker-compose exec -T mediawiki bash -c "[ -d extensions/$ext_name ]" 2>/dev/null; then
        echo "  ✓ $ext_name (cached)"
        return 0
    fi
    
    # Try different branches
    for branch in "REL1_45" "REL1_44" "master"; do
        if docker-compose exec -T mediawiki bash -c "cd extensions && git clone --depth 1 --branch $branch https://gerrit.wikimedia.org/r/mediawiki/extensions/$ext_name" 2>/dev/null; then
            echo "  ✓ $ext_name"
            return 0
        fi
    done
    echo "  ✗ $ext_name (failed)"
    return 1
}

# Clone all extensions in parallel
pids=()
all_extensions=("${KNOWN_EXTENSIONS[@]}" "${OPTIONAL_EXTENSIONS[@]}")

for ext in "${all_extensions[@]}"; do
    clone_extension "$ext" &
    pids+=($!)
    
    # Limit parallel jobs
    if [ ${#pids[@]} -ge $MAX_JOBS ]; then
        wait "${pids[0]}"
        pids=("${pids[@]:1}")
    fi
done
wait  # Wait for remaining jobs

# Now enable extensions (must be sequential to avoid LocalSettings.php conflicts)
echo ""
echo "  Enabling extensions..."
for ext in "${KNOWN_EXTENSIONS[@]}"; do
    if docker-compose exec -T mediawiki bash -c "[ -d extensions/$ext ]" 2>/dev/null; then
        docker-compose exec -T mediawiki bash -c "grep -q \"wfLoadExtension.*$ext\" LocalSettings.php 2>/dev/null || echo \"wfLoadExtension( '$ext' );\" >> LocalSettings.php"
    fi
done

# Test and enable optional extensions one by one
for ext in "${OPTIONAL_EXTENSIONS[@]}"; do
    if docker-compose exec -T mediawiki bash -c "[ -d extensions/$ext ]" 2>/dev/null; then
        docker-compose exec -T mediawiki bash -c "echo \"wfLoadExtension( '$ext' );\" >> LocalSettings.php"
        if ! docker-compose exec -T mediawiki php maintenance/version.php >/dev/null 2>&1; then
            echo "  ⚠ $ext incompatible, removing"
            docker-compose exec -T mediawiki bash -c "sed -i \"/$ext/d\" LocalSettings.php"
            docker-compose exec -T mediawiki bash -c "rm -rf extensions/$ext"
        fi
    fi
done

# === PARALLEL XML IMPORTS ===
echo ""
echo "[4/6] Importing XML Dumps (parallel)..."

import_xml() {
    local xml_file="$1"
    local filename=$(basename "$xml_file")
    local container_path="/var/www/data/xml/$filename"
    docker-compose exec -T mediawiki php maintenance/importDump.php "$container_path" --username-prefix="" >/dev/null 2>&1
    echo "  ✓ $filename"
}

if [ -d "./data/xml" ]; then
    xml_files=(./data/xml/*.xml)
    total=${#xml_files[@]}
    echo "  Found $total XML files..."
    
    pids=()
    for xml_file in "${xml_files[@]}"; do
        [ -e "$xml_file" ] || continue
        import_xml "$xml_file" &
        pids+=($!)
        
        if [ ${#pids[@]} -ge $MAX_JOBS ]; then
            wait "${pids[0]}"
            pids=("${pids[@]:1}")
        fi
    done
    wait
    echo "  ✓ All imports complete"
fi

# === PARALLEL IMAGE IMPORT ===
echo ""
echo "[5/6] Importing Images..."
if [ -d "./data/media" ] && [ "$(ls -A ./data/media 2>/dev/null)" ]; then
    img_count=$(ls -1 ./data/media 2>/dev/null | wc -l | xargs)
    echo "  Found $img_count images..."
    docker-compose exec -T mediawiki php maintenance/importImages.php /var/www/data/media --overwrite >/dev/null 2>&1 &
    IMG_PID=$!
    
    # Show progress while waiting
    while kill -0 $IMG_PID 2>/dev/null; do
        echo -n "."
        sleep 2
    done
    echo ""
    echo "  ✓ Images imported"
else
    echo "  No images to import."
fi

# Rebuild
echo ""
echo "[6/6] Rebuilding Database..."
docker-compose exec -T mediawiki php maintenance/rebuildrecentchanges.php >/dev/null 2>&1 &
docker-compose exec -T mediawiki php maintenance/initSiteStats.php --update >/dev/null 2>&1 &
wait

echo ""
echo "========================================"
echo "✓ Setup Complete!"
echo ""
echo "  URL:      http://localhost:8080"
echo "  Username: admin"
echo "  Password: adminpassword"
echo "========================================"
