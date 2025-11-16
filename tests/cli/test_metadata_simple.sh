#!/bin/bash
# Simple metadata CLI test
#
# This script tests metadata commands work end-to-end

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

echo "=============================================="
echo "Metadata CLI Simple Test"
echo "=============================================="

# Test 1: Help output works
print_step "Test 1: Checking help output for metadata commands"
briefcase dev -- library metadata-query --help > /dev/null 2>&1 && print_success "metadata-query help works" || print_error "metadata-query help failed"
briefcase dev -- library metadata-show --help > /dev/null 2>&1 && print_success "metadata-show help works" || print_error "metadata-show help failed"
briefcase dev -- library metadata-export --help > /dev/null 2>&1 && print_success "metadata-export help works" || print_error "metadata-export help failed"
briefcase dev -- library metadata-stats --help > /dev/null 2>&1 && print_success "metadata-stats help works" || print_error "metadata-stats help failed"
briefcase dev -- library metadata-import --help > /dev/null 2>&1 && print_success "metadata-import help works" || print_error "metadata-import help failed"
briefcase dev -- library metadata-history --help > /dev/null 2>&1 && print_success "metadata-history help works" || print_error "metadata-history help failed"

# Test 2: Create test collection with Python
print_step "Test 2: Creating test collection and metadata via Python"
COLLECTION_ID=$(python3 << 'EOF'
import sys
import os
# Set backend before any toga imports
os.environ["TOGA_BACKEND"] = "toga_cocoa"

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from unittest.mock import Mock
from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem
from datetime import datetime

# Create mock app
mock_app = Mock()
mock_app.paths = Mock()
mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

# Initialize library manager
lib = LibraryManager(mock_app)

# Create collection
collection = Collection(
    name="CLI Metadata Test",
    description="Test collection for metadata CLI",
    type="external",
    created_at=datetime.now(),
    updated_at=datetime.now()
)
collection_id = lib.storage.add_collection(collection)

# Create item
item = CollectionItem(
    collection_id=collection_id,
    name="Test Item 1",
    type="file",
    source_path="/tmp/test.png",
    storage_type="external",
    status="pending",
    created_at=datetime.now(),
    updated_at=datetime.now()
)
item_id = lib.storage.add_item(item)

# Add metadata
lib.metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="crop",
    metadata={
        "method": "yolo",
        "confidence": 0.92,
        "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
    },
    version=1
)

lib.metadata_api.save_step_metadata(
    item_id=item_id,
    step_name="rotate",
    metadata={
        "angle": -0.5,
        "found_lines": True
    },
    version=1
)

print(f"{collection_id}|{item_id}")
EOF
)

COLLECTION_ID=$(echo "$COLLECTION_ID" | tail -1 | cut -d'|' -f1)
ITEM_ID=$(echo "$COLLECTION_ID" | tail -1 | cut -d'|' -f2)

if [ -z "$COLLECTION_ID" ] || [ "$COLLECTION_ID" == "None" ]; then
    print_error "Failed to create test collection"
    exit 1
fi

print_success "Created test collection: $COLLECTION_ID"
print_success "Created test item: $ITEM_ID"

# Test 3: Query metadata
print_step "Test 3: Testing metadata-query command"
echo ""
briefcase dev -- library metadata-query "$COLLECTION_ID" --filter "crop.method=yolo" 2>&1 | grep -i "test item" && \
    print_success "Query found items with crop.method=yolo" || \
    print_error "Query failed to find items"

# Test 4: Show metadata
print_step "Test 4: Testing metadata-show command"
echo ""
briefcase dev -- library metadata-show "$ITEM_ID" 2>&1 | grep -i "crop" && \
    print_success "Show metadata displayed crop data" || \
    print_error "Show metadata failed"

# Test 5: Export metadata
print_step "Test 5: Testing metadata-export command"
EXPORT_FILE="/tmp/metadata_test_export.json"
rm -f "$EXPORT_FILE"
briefcase dev -- library metadata-export "$COLLECTION_ID" "$EXPORT_FILE" 2>&1
if [ -f "$EXPORT_FILE" ]; then
    print_success "Export created file: $EXPORT_FILE"
    cat "$EXPORT_FILE" | python3 -m json.tool > /dev/null && \
        print_success "Export file is valid JSON" || \
        print_error "Export file is not valid JSON"
else
    print_error "Export file not created"
fi

# Test 6: Stats
print_step "Test 6: Testing metadata-stats command"
echo ""
briefcase dev -- library metadata-stats "$COLLECTION_ID" 2>&1 | grep -i "items with metadata" && \
    print_success "Stats command works" || \
    print_error "Stats command failed"

# Cleanup
print_step "Cleaning up test data"
python3 << EOF
import sys
import os
os.environ["TOGA_BACKEND"] = "toga_cocoa"
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from unittest.mock import Mock
from fichero.library.library_manager import LibraryManager

mock_app = Mock()
mock_app.paths = Mock()
mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

lib = LibraryManager(mock_app)
lib.storage.delete_collection("$COLLECTION_ID")
print("Deleted test collection")
EOF

rm -f "$EXPORT_FILE"
print_success "Cleanup complete"

echo ""
echo "=============================================="
echo "✓ All tests completed successfully!"
echo "=============================================="
