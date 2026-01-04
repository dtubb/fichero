#!/bin/bash

# Script to add new Swift files to Xcode project
# Run this from the fichero directory

echo "======================================"
echo "Adding New Files to Xcode Project"
echo "======================================"
echo ""

PROJECT_PATH="Fichero/Fichero.xcodeproj"

# Check if project exists
if [ ! -d "$PROJECT_PATH" ]; then
    echo "ERROR: Could not find Xcode project at $PROJECT_PATH"
    exit 1
fi

echo "Found Xcode project: $PROJECT_PATH"
echo ""

# List of new files to add
NEW_FILES=(
    "Fichero/Fichero/Models/LayoutMode.swift"
    "Fichero/Fichero/Models/ItemTypeRegistry.swift"
    "Fichero/Fichero/Views/Menu/AddItemMenu.swift"
    "Fichero/Fichero/Views/Toolbar/MainToolbar.swift"
)

echo "Files to add:"
for file in "${NEW_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file (NOT FOUND)"
    fi
done
echo ""

echo "Opening Xcode..."
open "$PROJECT_PATH"

echo ""
echo "======================================"
echo "MANUAL STEPS REQUIRED"
echo "======================================"
echo ""
echo "Xcode should now be open. Please add the files manually:"
echo ""
echo "1. In Xcode Project Navigator, right-click 'Models' folder"
echo "2. Select 'Add Files to \"Fichero\"...'"
echo "3. Navigate to and select:"
echo "   - Fichero/Fichero/Models/LayoutMode.swift"
echo "   - Fichero/Fichero/Models/ItemTypeRegistry.swift"
echo ""
echo "4. Right-click 'Views/Menu' folder (or create 'Menu' folder if it doesn't exist)"
echo "5. Add: Fichero/Fichero/Views/Menu/AddItemMenu.swift"
echo ""
echo "6. Right-click 'Views' folder and create 'Toolbar' subfolder if it doesn't exist"
echo "7. Add: Fichero/Fichero/Views/Toolbar/MainToolbar.swift"
echo ""
echo "IMPORTANT:"
echo "  - UNCHECK 'Copy items if needed'"
echo "  - ENSURE 'Fichero' target is CHECKED"
echo ""
echo "After adding files, build with: ⌘B"
echo ""
echo "======================================"
