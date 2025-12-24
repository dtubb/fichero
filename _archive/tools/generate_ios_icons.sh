#!/bin/bash
# Generate iOS app icons for Fichero
# This script runs the Python icon generator from the project root

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🔧 Running iOS icon generator..."
echo "📁 Project root: $PROJECT_ROOT"
echo

# Change to project root and run the Python script
cd "$PROJECT_ROOT"
python tools/generate_ios_icons.py

echo
echo "✅ Icon generation complete!" 