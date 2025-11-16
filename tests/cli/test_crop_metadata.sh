#!/bin/bash
# CLI integration tests for crop tool library metadata
#
# This script tests the crop tool's integration with the library metadata system
# in both library mode and standalone mode.

set -e  # Exit on error

echo "=== Crop Tool Library Metadata Integration Tests ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0

# Function to print test result
pass_test() {
    echo -e "${GREEN}✅ PASS:${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail_test() {
    echo -e "${RED}❌ FAIL:${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

warn_test() {
    echo -e "${YELLOW}⚠️  WARN:${NC} $1"
}

# Setup test environment
TEST_DIR="/tmp/fichero_crop_test_$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "Test directory: $TEST_DIR"
echo ""

# Check if briefcase is available
if ! command -v briefcase &> /dev/null; then
    fail_test "briefcase command not found"
    echo "Please install briefcase: pip install briefcase"
    exit 1
fi

# Test 1: Standalone Mode - JSONL Creation
echo "Test 1: Standalone mode JSONL creation"
echo "--------------------------------------"

# Create test images using Python
python3 << 'EOF'
from PIL import Image
from pathlib import Path

# Create simple test images
Path("standalone_source").mkdir(exist_ok=True)
for i in range(3):
    img = Image.new('RGB', (1000, 800), color='white')
    img.save(f"standalone_source/test_{i}.jpg")

# Create manifest
import json
with open("standalone_manifest.jsonl", "w") as f:
    for i in range(3):
        entry = {
            "file": f"standalone_source/test_{i}.jpg",
            "type": "image"
        }
        f.write(json.dumps(entry) + '\n')

print("Created 3 test images and manifest")
EOF

# Note: crop tool requires YOLO model path
# For testing, we'll use contour mode with a dummy model path
DUMMY_MODEL="$TEST_DIR/dummy_model.pt"
touch "$DUMMY_MODEL"

# Run crop in standalone mode
mkdir -p standalone_output

echo "Running crop tool in standalone mode..."
# This will fail gracefully and use contour detection
PYTHONPATH=../src briefcase dev -- python -m fichero.tools.crop \
    standalone_source \
    standalone_manifest.jsonl \
    standalone_output \
    --model-path "$DUMMY_MODEL" \
    --format jpg \
    2>&1 | head -20 || true

# Check if JSONL was created
if [ -f "standalone_output/crop_manifest.jsonl" ]; then
    pass_test "JSONL manifest created in standalone mode"

    # Verify JSONL structure
    if grep -q '"source"' standalone_output/crop_manifest.jsonl && \
       grep -q '"details"' standalone_output/crop_manifest.jsonl && \
       grep -q '"outputs"' standalone_output/crop_manifest.jsonl; then
        pass_test "JSONL has correct structure"
    else
        fail_test "JSONL missing required fields"
    fi

    # Verify metadata details
    if grep -q '"method"' standalone_output/crop_manifest.jsonl && \
       grep -q '"box"' standalone_output/crop_manifest.jsonl; then
        pass_test "JSONL contains crop metadata"
    else
        fail_test "JSONL missing crop metadata"
    fi
else
    fail_test "JSONL manifest not created"
fi

echo ""

# Test 2: Validation Function
echo "Test 2: Crop box validation"
echo "----------------------------"

# Test validation using Python
python3 << 'EOF'
import sys
sys.path.insert(0, '../src')

from fichero.tools.crop import validate_crop_box

# Test valid box
is_valid, error = validate_crop_box(
    {"x1": 100, "y1": 50, "x2": 800, "y2": 650},
    1000, 700
)
if is_valid and error is None:
    print("PASS: Valid crop box accepted")
else:
    print(f"FAIL: Valid crop box rejected: {error}")
    sys.exit(1)

# Test negative coordinates
is_valid, error = validate_crop_box(
    {"x1": -10, "y1": 50, "x2": 800, "y2": 650},
    1000, 700
)
if not is_valid and "non-negative" in error:
    print("PASS: Negative coordinates rejected")
else:
    print("FAIL: Negative coordinates should be rejected")
    sys.exit(1)

# Test exceeds bounds
is_valid, error = validate_crop_box(
    {"x1": 100, "y1": 50, "x2": 1200, "y2": 650},
    1000, 700
)
if not is_valid and "exceeds" in error:
    print("PASS: Out-of-bounds coordinates rejected")
else:
    print("FAIL: Out-of-bounds coordinates should be rejected")
    sys.exit(1)

# Test zero area
is_valid, error = validate_crop_box(
    {"x1": 100, "y1": 50, "x2": 100, "y2": 650},
    1000, 700
)
if not is_valid and "positive area" in error:
    print("PASS: Zero-area box rejected")
else:
    print("FAIL: Zero-area box should be rejected")
    sys.exit(1)

print("\nAll validation tests passed")
EOF

if [ $? -eq 0 ]; then
    pass_test "Crop box validation working correctly"
else
    fail_test "Crop box validation has issues"
fi

echo ""

# Test 3: Library Mode (requires full library setup)
echo "Test 3: Library mode metadata storage"
echo "--------------------------------------"

warn_test "Library mode testing requires full library and Director setup"
warn_test "This test is a placeholder for integration testing"
echo ""
echo "To test library mode manually:"
echo "1. briefcase dev -- library add 'Test Collection' --type local --source /path/to/images"
echo "2. briefcase dev -- library add-item <collection_id> folder /path/to/folder"
echo "3. briefcase dev -- library process <collection_id> --plan 'Crop Only' --workflow 'crop'"
echo "4. briefcase dev -- library metadata-show <item_id> --step crop"
echo ""

# Cleanup
echo "Test Summary"
echo "============"
echo -e "Tests passed: ${GREEN}${TESTS_PASSED}${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "Tests failed: ${RED}${TESTS_FAILED}${NC}"
else
    echo -e "Tests failed: ${TESTS_FAILED}"
fi
echo ""

# Optional: Clean up test directory
read -p "Clean up test directory? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd /tmp
    rm -rf "$TEST_DIR"
    echo "Test directory cleaned up"
else
    echo "Test directory preserved at: $TEST_DIR"
fi

# Exit with appropriate code
if [ $TESTS_FAILED -gt 0 ]; then
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
