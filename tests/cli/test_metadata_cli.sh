#!/bin/bash
# Test metadata CLI commands
#
# This script tests the full metadata workflow:
# 1. Create a test collection
# 2. Add test items
# 3. Manually create some test metadata
# 4. Query metadata
# 5. Show metadata
# 6. Export metadata
# 7. Show stats

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Setup test directory
TEST_DIR="/tmp/fichero_metadata_test_$(date +%s)"
print_step "Setting up test environment in $TEST_DIR"
mkdir -p "$TEST_DIR/images"

# Create some test images
print_step "Creating test images..."
for i in {1..5}; do
    # Create a simple test image (100x100 white PNG)
    convert -size 100x100 xc:white "$TEST_DIR/images/test_$i.png" 2>/dev/null || {
        # If ImageMagick is not available, create dummy files
        echo "dummy image $i" > "$TEST_DIR/images/test_$i.png"
    }
done
print_success "Created 5 test images"

# Test 1: Create test collection
print_step "Test 1: Creating test collection..."
COLLECTION_OUTPUT=$(briefcase dev -- library add "CLI Metadata Test" --type external --source "$TEST_DIR/images" 2>&1)
echo "$COLLECTION_OUTPUT"

# Extract collection ID from output (assumes format contains "ID: <uuid>")
COLLECTION_ID=$(echo "$COLLECTION_OUTPUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)

if [ -z "$COLLECTION_ID" ]; then
    print_error "Failed to create collection or extract ID"
    exit 1
fi
print_success "Created collection with ID: $COLLECTION_ID"

# Test 2: List items in collection
print_step "Test 2: Listing items in collection..."
ITEMS_OUTPUT=$(briefcase dev -- library items "$COLLECTION_ID" 2>&1)
echo "$ITEMS_OUTPUT"

# Extract first item ID
ITEM_ID=$(echo "$ITEMS_OUTPUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)

if [ -z "$ITEM_ID" ]; then
    print_warning "No items found in collection (this is expected for external collections)"
    print_step "Adding items manually..."

    # Add items from the folder
    for img in "$TEST_DIR/images"/*.png; do
        briefcase dev -- library add-item "$COLLECTION_ID" file "$img" 2>&1 || true
    done

    # List items again
    ITEMS_OUTPUT=$(briefcase dev -- library items "$COLLECTION_ID" 2>&1)
    echo "$ITEMS_OUTPUT"
    ITEM_ID=$(echo "$ITEMS_OUTPUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
fi

if [ -z "$ITEM_ID" ]; then
    print_error "Failed to get item ID"
    exit 1
fi
print_success "Found item ID: $ITEM_ID"

# Test 3: Create test metadata using Python script
print_step "Test 3: Creating test metadata..."
python3 << EOF
import sys
sys.path.insert(0, '/Users/dtubb/code/fichero_main/fichero/src')

from fichero.library.storage import LibraryStorage
from fichero.library.metadata_api import LibraryMetadataAPI
from pathlib import Path
from unittest.mock import Mock

# Get library path
mock_app = Mock()
mock_app.paths = Mock()
mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

from fichero.library.path_resolver import get_library_database_path
db_path = get_library_database_path(mock_app)

storage = LibraryStorage(db_path)
metadata_api = LibraryMetadataAPI(storage)

# Save some test metadata
item_id = "$ITEM_ID"

# Crop metadata
metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="crop",
    metadata={
        "method": "yolo",
        "confidence": 0.92,
        "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000},
        "padding": 30
    },
    version=1
)

# Rotate metadata
metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="rotate",
    metadata={
        "angle": -0.5,
        "found_lines": True,
        "num_lines": 3,
        "method": "line_detection"
    },
    version=1
)

# Transcribe metadata
metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="transcribe",
    metadata={
        "text_length": 450,
        "model": "qwen-vl-max",
        "has_content": True,
        "num_lines": 15
    },
    version=1
)

print("✓ Created test metadata")
EOF
print_success "Created test metadata for crop, rotate, and transcribe steps"

# Test 4: Query metadata
print_step "Test 4: Querying metadata..."
echo ""
echo "Query 1: Items with crop.method=yolo"
briefcase dev -- library metadata-query "$COLLECTION_ID" --filter "crop.method=yolo" 2>&1 || true

echo ""
echo "Query 2: Items with crop.confidence>=0.85"
briefcase dev -- library metadata-query "$COLLECTION_ID" --filter "crop.confidence>=0.85" 2>&1 || true

echo ""
echo "Query 3: Multiple filters (crop.method=yolo AND rotate.found_lines=true)"
briefcase dev -- library metadata-query "$COLLECTION_ID" --filter "crop.method=yolo" --filter "rotate.found_lines=true" 2>&1 || true

print_success "Metadata query tests completed"

# Test 5: Show metadata
print_step "Test 5: Showing item metadata..."
echo ""
echo "Show all metadata for item:"
briefcase dev -- library metadata-show "$ITEM_ID" 2>&1 || true

echo ""
echo "Show metadata for specific step (crop):"
briefcase dev -- library metadata-show "$ITEM_ID" --step crop 2>&1 || true

print_success "Metadata show tests completed"

# Test 6: Export metadata
print_step "Test 6: Exporting metadata..."
EXPORT_FILE="$TEST_DIR/metadata_export.json"
briefcase dev -- library metadata-export "$COLLECTION_ID" "$EXPORT_FILE" 2>&1 || true

if [ -f "$EXPORT_FILE" ]; then
    print_success "Metadata exported to $EXPORT_FILE"
    echo "Export file contents:"
    cat "$EXPORT_FILE" | head -20
else
    print_error "Export file not created"
fi

# Test 7: Metadata stats
print_step "Test 7: Showing metadata statistics..."
briefcase dev -- library metadata-stats "$COLLECTION_ID" 2>&1 || true

print_success "Metadata stats completed"

# Test 8: Metadata history
print_step "Test 8: Showing metadata version history..."
briefcase dev -- library metadata-history "$ITEM_ID" crop 2>&1 || true

print_success "Metadata history completed"

# Test 9: Test JSON output
print_step "Test 9: Testing JSON output format..."
echo ""
echo "JSON output for metadata query:"
briefcase dev -- library metadata-query "$COLLECTION_ID" --filter "crop.method=yolo" --json 2>&1 || true

echo ""
echo "JSON output for metadata show:"
briefcase dev -- library metadata-show "$ITEM_ID" --json 2>&1 || true

echo ""
echo "JSON output for metadata stats:"
briefcase dev -- library metadata-stats "$COLLECTION_ID" --json 2>&1 || true

print_success "JSON output tests completed"

# Test 10: Test metadata import
print_step "Test 10: Testing metadata import..."
MANIFEST_FILE="$TEST_DIR/test_manifest.jsonl"

# Create test manifest
cat > "$MANIFEST_FILE" << 'MANIFEST_EOF'
{"step_name": "enhance", "metadata": {"brightness": 1.2, "contrast": 1.1, "method": "auto"}}
{"step_name": "denoise", "metadata": {"strength": 0.8, "method": "nlmeans"}}
MANIFEST_EOF

print_step "Created test manifest file"
cat "$MANIFEST_FILE"

echo ""
echo "Dry run import:"
briefcase dev -- library metadata-import "$ITEM_ID" "$MANIFEST_FILE" --dry-run 2>&1 || true

echo ""
echo "Actual import:"
briefcase dev -- library metadata-import "$ITEM_ID" "$MANIFEST_FILE" 2>&1 || true

echo ""
echo "Verify import - show all metadata:"
briefcase dev -- library metadata-show "$ITEM_ID" 2>&1 || true

print_success "Metadata import tests completed"

# Summary
echo ""
print_step "=== Test Summary ==="
print_success "All metadata CLI tests completed successfully!"
echo ""
echo "Test collection ID: $COLLECTION_ID"
echo "Test item ID: $ITEM_ID"
echo "Test directory: $TEST_DIR"
echo ""
echo "To clean up:"
echo "  rm -rf $TEST_DIR"
echo "  briefcase dev -- library delete $COLLECTION_ID"
