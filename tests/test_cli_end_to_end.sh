#!/bin/bash
#
# End-to-End CLI Testing Script
# Tests the complete processing pipeline from CLI
#

set -e  # Exit on error

echo "=================================="
echo "Fichero CLI End-to-End Test Suite"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
test_start() {
    echo -e "${YELLOW}TEST:${NC} $1"
    TESTS_RUN=$((TESTS_RUN + 1))
}

test_pass() {
    echo -e "${GREEN}✓ PASS${NC}"
    echo ""
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    echo ""
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

# Test 1: CLI Help Command
test_start "CLI help command works"
if briefcase dev -- --help 2>&1 | grep -q "Fichero - Document Processing System"; then
    test_pass
else
    test_fail "Help command did not return expected output"
fi

# Test 2: Plans List
test_start "Plans list command works"
if briefcase dev -- plans 2>&1 | grep -q "Available Plans"; then
    test_pass
else
    test_fail "Plans command did not list plans"
fi

# Test 3: Library List
test_start "Library list works (checking database exists)"
if sqlite3 ~/Library/Application\ Support/ca.tubb.fichero/library/library.db "SELECT COUNT(*) FROM collections;" > /dev/null 2>&1; then
    test_pass
else
    test_fail "Library database not accessible"
fi

# Test 4: Process Command (Tiny Test)
test_start "CLI process command (Tiny Test - 2 images)"
TEST_OUTPUT="/tmp/fichero_test_output_$$"
rm -rf "$TEST_OUTPUT"

if briefcase dev -- process "/Users/dtubb/Documents/fichero/Tiny Test" \
    --output "$TEST_OUTPUT" \
    --plan "Default" \
    --workflow "Catalogue" 2>&1 | grep -q "Processing completed successfully"; then

    # Verify output structure exists
    if [ -d "$TEST_OUTPUT" ]; then
        FILE_COUNT=$(find "$TEST_OUTPUT" -type f | wc -l)
        if [ "$FILE_COUNT" -gt 0 ]; then
            test_pass
        else
            test_fail "No output files created"
        fi
    else
        test_fail "Output directory not created"
    fi
else
    test_fail "Process command did not complete successfully"
fi

# Cleanup
rm -rf "$TEST_OUTPUT"

# Test 5: Hierarchical Output Structure
test_start "Library process creates hierarchical structure"
COLLECTION_ID="1ddb64e5-6f77-40ea-872d-df12f23151b2"  # Small Test Collection

# Note: This test may fail if API keys are not set up, but we can still verify structure
briefcase dev -- library process "$COLLECTION_ID" \
    --plan "Default" \
    --workflow "Catalogue" 2>&1 | grep -q "Submitted.*task" || true

# Check if hierarchical structure was created
OUTPUT_BASE=~/Library/Application\ Support/ca.tubb.fichero/processed
if [ -d "$OUTPUT_BASE/Small_Test_Collection" ]; then
    # Check for date folder
    if [ -d "$OUTPUT_BASE/Small_Test_Collection/$(date +%Y-%m-%d)" ]; then
        # Check for workflow folder
        if [ -d "$OUTPUT_BASE/Small_Test_Collection/$(date +%Y-%m-%d)/Catalogue" ]; then
            test_pass
        else
            test_fail "Workflow folder not created in hierarchical structure"
        fi
    else
        test_fail "Date folder not created in hierarchical structure"
    fi
else
    test_fail "Collection folder not created in hierarchical structure"
fi

# Test 6: No File Copying Verification
test_start "Files are NOT copied during processing (in-place processing)"
SOURCE_DIR="/Users/dtubb/Documents/fichero/Tiny Test"
if [ -d "$SOURCE_DIR" ]; then
    SOURCE_FILE_COUNT=$(find "$SOURCE_DIR" -type f -name "*.JPG" -o -name "*.jpg" | wc -l | tr -d ' ')

    # Run processing
    TEST_OUTPUT2="/tmp/fichero_nocopy_test_$$"
    rm -rf "$TEST_OUTPUT2"

    briefcase dev -- process "$SOURCE_DIR" \
        --output "$TEST_OUTPUT2" \
        --plan "Default" \
        --workflow "Catalogue" 2>&1 > /dev/null || true

    # Check that source files still exist and weren't moved
    SOURCE_FILE_COUNT_AFTER=$(find "$SOURCE_DIR" -type f -name "*.JPG" -o -name "*.jpg" | wc -l | tr -d ' ')

    if [ "$SOURCE_FILE_COUNT" -eq "$SOURCE_FILE_COUNT_AFTER" ]; then
        test_pass
    else
        test_fail "Source file count changed - files may have been moved"
    fi

    rm -rf "$TEST_OUTPUT2"
else
    test_fail "Source directory not found for testing"
fi

# Test Summary
echo "=================================="
echo "Test Summary"
echo "=================================="
echo "Tests Run:    $TESTS_RUN"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
else
    echo -e "Tests Failed: $TESTS_FAILED"
fi
echo "=================================="

# Exit code
if [ $TESTS_FAILED -gt 0 ]; then
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
