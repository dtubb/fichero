#!/bin/bash
# Clear Python cache to fix method name issues

echo "🧹 Clearing Python cache..."

# Navigate to project root
cd "$(dirname "$0")"

# Clear __pycache__ directories
echo "  Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "  ✓ Removed __pycache__ directories"

# Clear .pyc files
echo "  Removing .pyc files..."
find . -name "*.pyc" -delete 2>/dev/null
echo "  ✓ Removed .pyc files"

# Clear .pyo files (optimized bytecode)
echo "  Removing .pyo files..."
find . -name "*.pyo" -delete 2>/dev/null
echo "  ✓ Removed .pyo files"

echo ""
echo "✅ Cache cleared successfully!"
echo ""
echo "Next steps:"
echo "  1. Kill any running Fichero processes: pkill -f fichero"
echo "  2. Restart the app: briefcase dev"
echo ""
