#!/bin/bash
# Run the Widget List Demo
# Tests all 6 widget list renderers with mock data
#
# Run from project root: src/fichero/shared/widgets/list_widget/demos/run_widget_demo.sh

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Navigate to project root (5 levels up from demos folder)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

cd "$PROJECT_ROOT"
PYTHONPATH=src python3 "$SCRIPT_DIR/widget_list_demo.py"
