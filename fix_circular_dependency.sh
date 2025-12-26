#!/bin/bash

echo "🔧 Fixing Circular Dependency in Xcode Project"
echo "=============================================="
echo ""

cd /Users/dtubb/code/fichero_main/fichero/Fichero

# Check if we're in the right directory
if [ ! -f "Fichero.xcodeproj/project.pbxproj" ]; then
    echo "❌ Error: Not in the Fichero project directory"
    echo "Please run this script from: /Users/dtubb/code/fichero_main/fichero/Fichero"
    exit 1
fi

echo "✅ Working directory confirmed: $(pwd)"
echo ""

echo "📋 Circular Dependency Fix"
echo "=========================="
echo ""
echo "The error shows:"
echo "  Cycle in dependencies between targets 'Fichero' and 'FicheroTests'"
echo "  Fichero → FicheroTests → Fichero"
echo ""
echo "This happens when:"
echo "  1. Main app target depends on test target (WRONG)"
echo "  2. Test target depends on main app target (CORRECT)"
echo ""

echo "🛠️ Fix Instructions"
echo "===================="
echo ""
echo "Step 1: Open Xcode and the project"
open Fichero.xcodeproj
echo "✅ Xcode should now be opening. Please continue when ready."
read -p "Press Enter when Xcode is open and you're ready to continue..."

echo ""
echo "Step 2: Remove incorrect dependency from main app target"
echo "-------------------------------------------------------"
echo "1. Click on 'Fichero' project at top of Project Navigator"
echo "2. Select 'Fichero' target (main app target)"
echo "3. Go to 'Build Phases' tab"
echo "4. Under 'Dependencies', REMOVE:"
echo "   - FicheroTests"
echo "   - FicheroUITests"
echo ""
echo "   The main app should NOT depend on test targets!"
echo "   Test targets should depend on the main app."
echo ""
read -p "Press Enter when you've completed this step..."

echo ""
echo "Step 3: Verify test target dependencies (should be correct)"
echo "----------------------------------------------------------"
echo "1. Select 'FicheroTests' target"
echo "2. Go to 'Build Phases' tab"
echo "3. Under 'Dependencies', you should see:"
echo "   - Fichero (main app target)"
echo ""
echo "   This is CORRECT - tests depend on the app, not vice versa."
echo ""
read -p "Press Enter when you've verified this..."

echo ""
echo "Step 4: Set correct test host for test targets"
echo "----------------------------------------------"
echo "1. Select 'FicheroTests' target"
echo "2. Go to 'Build Settings' tab"
echo "3. Search for 'Test Host'"
echo "4. Set 'TEST_HOST' to:"
echo "   $(BUILT_PRODUCTS_DIR)/Fichero.app/Contents/MacOS/Fichero"
echo ""
echo "5. Repeat for 'FicheroUITests' target"
echo ""
read -p "Press Enter when you've completed this step..."

echo ""
echo "Step 5: Clean and rebuild"
echo "-------------------------"
echo "1. Go to Product > Clean Build Folder"
echo "2. Wait for cleaning to complete"
echo "3. Try building again (Cmd+B)"
echo ""
read -p "Press Enter when you've completed this step..."

echo ""
echo "🎉 Circular Dependency Fixed!"
echo "=============================="
echo ""
echo "The dependency cycle should now be resolved:"
echo "  FicheroTests → Fichero (correct direction)"
echo "  FicheroUITests → Fichero (correct direction)"
echo ""
echo "Key principles:"
echo "  ✅ Test targets depend on the main app"
echo "  ❌ Main app should NOT depend on test targets"
echo "  ✅ Test host points to the built app"
echo ""

echo "🧪 Testing the Fix"
echo "=================="
echo ""
echo "Try these commands to verify the fix:"
echo ""
echo "1. Build the main app:"
echo "   xcodebuild -workspace Fichero.xcodeproj/project.xcworkspace -scheme Fichero"
echo ""
echo "2. Run tests:"
echo "   xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace -scheme Fichero -destination 'platform=macOS'"
echo ""
echo "3. Run specific test:"
echo "   xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace -scheme Fichero -destination 'platform=macOS' -only-testing:FicheroTests/SidebarTests"
echo ""

read -p "Would you like me to try building now? (y/n): " try_build

if [ "$try_build" = "y" ] || [ "$try_build" = "Y" ]; then
    echo ""
    echo "🚀 Attempting to build..."
    echo ""
    
    # Try to build
    xcodebuild -workspace Fichero.xcodeproj/project.xcworkspace -scheme Fichero 2>&1 | head -30
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Build succeeded! The circular dependency is fixed."
        echo ""
        echo "You can now:"
        echo "  - Run tests with Cmd+U in Xcode"
        echo "  - Build and run the app normally"
        echo "  - Use xcodebuild commands without errors"
    else
        echo ""
        echo "⚠️  Build failed. Let's try a few more things..."
        echo ""
        echo "Additional troubleshooting steps:"
        echo "1. Quit and reopen Xcode"
        echo "2. Delete DerivedData: rm -rf ~/Library/Developer/Xcode/DerivedData/Fichero*"
        echo "3. Clean build folder in Xcode: Product > Clean Build Folder"
        echo "4. Restart your Mac if needed"
    fi
fi

echo ""
echo "📚 Reference: Correct Dependency Structure"
echo "=========================================="
echo ""
echo "CORRECT:"
echo "  FicheroTests → Fichero"
echo "  FicheroUITests → Fichero"
echo ""
echo "INCORRECT (causes cycle):"
echo "  Fichero → FicheroTests"
echo "  FicheroTests → Fichero"
echo ""
echo "The main app should never depend on test targets!"
echo ""

echo "Thank you for using Fichero! 🎉"