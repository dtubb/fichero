#!/bin/bash

# Fichero Parallel Testing Script
# Tests desktop, desktop mobile mode, and iOS simultaneously

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
mkdir -p logs

# Function to get iOS device UUID
get_ios_device_uuid() {
    local devices=$(xcrun simctl list devices available | grep "iPhone" | head -1)
    if [[ $devices =~ ([A-F0-9-]{36}) ]]; then
        echo "${BASH_REMATCH[1]}"
    else
        echo "booted"  # Fallback to booted device
    fi
}

# Function to activate venv and run desktop
run_desktop() {
    echo -e "${BLUE}🖥️  Starting Desktop testing...${NC}"
    
    # Check if we're in the right directory
    if [ -d "fichero" ] && [ -f "fichero/pyproject.toml" ]; then
        # We're in the fichero_main directory, need to go to fichero
        echo -e "${BLUE}🖥️  Changing to fichero directory${NC}"
        cd fichero
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    elif [ -f "pyproject.toml" ]; then
        # We're already in the fichero directory
        echo -e "${BLUE}🖥️  Already in fichero directory${NC}"
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    else
        echo -e "${RED}❌ Error: Cannot find fichero project directory${NC}"
        return 1
    fi
    
    # Run desktop version with environment variable
    echo -e "${BLUE}🖥️  Running desktop version...${NC}"
    FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev > ./logs/desktop.log 2>&1
}

# Function to activate venv and run desktop in mobile mode
run_desktop_mobile_mode() {
    echo -e "${YELLOW}🖥️📱 Starting Desktop Mobile Mode testing...${NC}"
    
    # Check if we're in the right directory
    if [ -d "fichero" ] && [ -f "fichero/pyproject.toml" ]; then
        # We're in the fichero_main directory, need to go to fichero
        echo -e "${YELLOW}🖥️📱 Changing to fichero directory${NC}"
        cd fichero
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    elif [ -f "pyproject.toml" ]; then
        # We're already in the fichero directory
        echo -e "${YELLOW}🖥️📱 Already in fichero directory${NC}"
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    else
        echo -e "${RED}❌ Error: Cannot find fichero project directory${NC}"
        return 1
    fi
    
    # Run desktop version with mobile environment variable
    echo -e "${YELLOW}🖥️📱 Running desktop with mobile UI...${NC}"
    FORCE_MOBILE_UI=true TOGA_BACKEND=toga_cocoa briefcase dev > ./logs/desktop_mobile.log 2>&1
}

# Function to run iOS only
run_ios_only() {
    echo -e "${GREEN}📱 Starting iOS-only testing...${NC}"
    
    # Check if we're in the right directory
    if [ -d "fichero" ] && [ -f "fichero/pyproject.toml" ]; then
        # We're in the fichero_main directory, need to go to fichero
        echo -e "${GREEN}📱 Changing to fichero directory${NC}"
        cd fichero
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    elif [ -f "pyproject.toml" ]; then
        # We're already in the fichero directory
        echo -e "${GREEN}📱 Already in fichero directory${NC}"
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    else
        echo -e "${RED}❌ Error: Cannot find fichero project directory${NC}"
        return 1
    fi
    
    # Get device UUID automatically
    local device_uuid=$(get_ios_device_uuid)
    echo -e "${GREEN}📱 Using iOS device: $device_uuid${NC}"
    
    # First build/update the iOS app
    echo -e "${GREEN}📱 Building/updating iOS app...${NC}"
    FORCE_MOBILE_UI=true briefcase build iOS -u > ./logs/mobile_ios_build.log 2>&1
    
    # Then run the iOS simulator
    echo -e "${GREEN}📱 Running iOS simulator...${NC}"
    FORCE_MOBILE_UI=true briefcase run iOS -d "$device_uuid" > ./logs/mobile_ios.log 2>&1
}

# Function to test CLI without Toga
run_cli_test() {
    echo -e "${BLUE}💻 Starting CLI testing...${NC}"
    
    # Check if we're in the right directory
    if [ -d "fichero" ] && [ -f "fichero/pyproject.toml" ]; then
        # We're in the fichero_main directory, need to go to fichero
        echo -e "${BLUE}💻 Changing to fichero directory${NC}"
        cd fichero
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    elif [ -f "pyproject.toml" ]; then
        # We're already in the fichero directory
        echo -e "${BLUE}💻 Already in fichero directory${NC}"
        # Activate venv using absolute path
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    else
        echo -e "${RED}❌ Error: Cannot find fichero project directory${NC}"
        return 1
    fi
    
    # Test basic CLI functionality using briefcase dev
    echo -e "${BLUE}💻 Testing CLI help...${NC}"
    briefcase dev -- --help > ./logs/cli_help.log 2>&1
    
    echo -e "${BLUE}💻 Testing CLI version...${NC}"
    briefcase dev -- --version > ./logs/cli_version.log 2>&1
    
    echo -e "${BLUE}💻 Testing CLI info command...${NC}"
    briefcase dev -- info > ./logs/cli_info.log 2>&1
    
    echo -e "${BLUE}💻 Testing CLI list-plans command...${NC}"
    briefcase dev -- list-plans > ./logs/cli_list_plans.log 2>&1
    
    echo -e "${BLUE}💻 Testing CLI backend info command...${NC}"
    briefcase dev -- backend info > ./logs/cli_backend_info.log 2>&1
    
    echo -e "${BLUE}💻 Testing CLI library commands...${NC}"
    echo -e "${BLUE}💻   - Library help...${NC}"
    briefcase dev -- library --help > ./logs/cli_library_help.log 2>&1
    
    echo -e "${BLUE}💻   - Library list...${NC}"
    briefcase dev -- library list > ./logs/cli_library_list.log 2>&1
    
    echo -e "${BLUE}💻   - Library add test collection...${NC}"
    briefcase dev -- library add "CLI Test Collection" --type local --description "Created by CLI testing script" > ./logs/cli_library_add.log 2>&1
    
    echo -e "${BLUE}💻   - Library list after add...${NC}"
    briefcase dev -- library list > ./logs/cli_library_list_after.log 2>&1
    
    echo -e "${GREEN}✅ CLI testing completed! Check logs in ./logs/cli_*.log${NC}"
}

# Function to run unit tests first
run_unit_tests() {
    echo -e "${BLUE}🧪 Running unit tests first...${NC}"

    # Check if we're in the right directory
    if [ -d "fichero" ] && [ -f "fichero/pyproject.toml" ]; then
        cd fichero
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    elif [ -f "pyproject.toml" ]; then
        source /Users/dtubb/code/fichero_main/fichero/.venv/bin/activate
    else
        echo -e "${RED}❌ Error: Cannot find fichero project directory${NC}"
        return 1
    fi

    echo -e "${BLUE}🧪 Running unit test suite...${NC}"

    # Run multiple test suites
    echo -e "${BLUE}🧪   - Testing library service...${NC}"
    PYTHONPATH=src python tests/unit/test_library_service.py > ./logs/unit_tests_library.log 2>&1
    local library_tests=$?

    echo -e "${BLUE}🧪   - Testing URL import...${NC}"
    PYTHONPATH=src python -c "
import unittest
import sys
sys.path.insert(0, 'tests/unit')
from test_url_import import TestBulkImportCommands
suite = unittest.TestSuite()
suite.addTest(TestBulkImportCommands('test_url_format_validation'))
suite.addTest(TestBulkImportCommands('test_extract_urls_from_text_cli'))
suite.addTest(TestBulkImportCommands('test_generate_url_name'))
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
exit(0 if result.wasSuccessful() else 1)
" > ./logs/unit_tests_url.log 2>&1
    local url_tests=$?

    echo -e "${BLUE}🧪   - Testing center pane...${NC}"
    PYTHONPATH=src python tests/unit/test_center_pane.py > ./logs/unit_tests_center_pane.log 2>&1
    local center_pane_tests=$?

    echo -e "${BLUE}🧪   - Testing window integration...${NC}"
    PYTHONPATH=src python -m unittest tests.unit.test_window_integration -v > ./logs/unit_tests_window.log 2>&1
    local window_tests=$?

    echo -e "${BLUE}🧪   - Testing preview integration...${NC}"
    PYTHONPATH=src python tests/unit/test_preview_integration.py > ./logs/unit_tests_preview.log 2>&1
    local preview_tests=$?

    local test_exit_code=$((library_tests + url_tests + center_pane_tests + window_tests + preview_tests))

    if [ $test_exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ Unit tests passed! Proceeding with GUI tests...${NC}"
        return 0
    else
        echo -e "${RED}❌ Unit tests failed! Check ./logs/unit_tests.log for details${NC}"
        echo -e "${YELLOW}⚠️  Continuing with GUI tests anyway for debugging...${NC}"
        return $test_exit_code
    fi
}

# Function to run all four modes in parallel
run_all_parallel() {
    echo -e "${BLUE}🚀 Starting comprehensive testing...${NC}"

    # Run unit tests first
    run_unit_tests
    local test_result=$?

    echo -e "${BLUE}🚀 Starting all three GUI modes in parallel...${NC}"

    # Start desktop in background
    run_desktop &
    local desktop_pid=$!
    echo -e "${BLUE}🖥️  Desktop started with PID: $desktop_pid${NC}"
    
    # Wait a moment for desktop to start
    sleep 2
    
    # Start desktop mobile mode in background
    run_desktop_mobile_mode &
    local mobile_pid=$!
    echo -e "${YELLOW}🖥️📱 Desktop mobile mode started with PID: $mobile_pid${NC}"
    
    # Wait a moment for mobile mode to start
    sleep 2
    
    # Start iOS in background
    run_ios_only &
    local ios_pid=$!
    echo -e "${GREEN}📱 iOS started with PID: $ios_pid${NC}"
    
    # Wait a moment for iOS to start
    sleep 2
    
    # Start CLI testing in background
    run_cli_test &
    local cli_pid=$!
    echo -e "${BLUE}💻 CLI testing started with PID: $cli_pid${NC}"
    
    echo -e "${BLUE}🚀 All four modes running in parallel!${NC}"
    echo -e "${BLUE}📊 Check logs in the logs/ directory${NC}"
    echo -e "${BLUE}🖥️  Desktop PID: $desktop_pid${NC}"
    echo -e "${YELLOW}🖥️📱 Mobile PID: $mobile_pid${NC}"
    echo -e "${GREEN}📱 iOS PID: $ios_pid${NC}"
    echo -e "${BLUE}💻 CLI PID: $cli_pid${NC}"
    
    # Wait for all processes
    wait
}

# Function to show help
show_help() {
    echo "Fichero Parallel Testing Script"
    echo ""
    echo "Usage:"
    echo "  $0                    - Run unit tests first, then all GUI modes in parallel"
    echo "  $0 tests              - Run unit tests only"
    echo "  $0 desktop            - Run desktop mode only"
    echo "  $0 mobile             - Run desktop mobile mode only"
    echo "  $0 ios                - Run iOS simulator only"
    echo "  $0 cli                - Test CLI without Toga"
    echo "  $0 help               - Show this help"
    echo ""
    echo "Environment Variables:"
    echo "  FORCE_MOBILE_UI=true  - Force mobile UI mode"
    echo "  FORCE_MOBILE_UI=false - Force desktop UI mode"
    echo ""
    echo "Logs are saved to the logs/ directory"
}

# Main execution logic
case "${1:-all}" in
    "tests")
        run_unit_tests
        ;;
    "desktop")
        run_desktop
        ;;
    "mobile")
        run_desktop_mobile_mode
        ;;
    "ios")
        run_ios_only
        ;;
    "cli")
        run_cli_test
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    "all"|*)
        run_all_parallel
        ;;
esac 