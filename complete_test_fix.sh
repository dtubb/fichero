#!/bin/bash

echo "🎯 Complete Test Configuration Fix for Fichero"
echo "============================================"
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

echo "🔍 Diagnosing Current State"
echo "==========================="
echo ""

# Check current schemes
echo "Current schemes:"
xcodebuild -list -workspace Fichero.xcodeproj/project.xcworkspace 2>/dev/null | grep -A 10 "Schemes:" || echo "  (None found)"
echo ""

# Check test directories
echo "Test directories:"
if [ -d "FicheroTests" ]; then
    echo "  ✅ FicheroTests exists ($(find FicheroTests -name "*.swift" | wc -l) test files)"
else
    echo "  ❌ FicheroTests missing"
fi

if [ -d "FicheroUITests" ]; then
    echo "  ✅ FicheroUITests exists ($(find FicheroUITests -name "*.swift" | wc -l) test files)"
else
    echo "  ❌ FicheroUITests missing"
fi

echo ""
echo "📋 Issue Analysis"
echo "================"
echo ""
echo "Based on your screenshot, the issue is:"
echo "  'Cannot run tests - No testable targets found'"
echo ""
echo "This happens because:"
echo "  1. Test targets are not properly configured"
echo "  2. Scheme is not set up for testing"
echo "  3. Test targets may not be properly linked to main app"
echo ""

echo "🛠️ Complete Fix Process"
echo "======================="
echo ""
echo "I will guide you through the complete setup process."
echo "This will take about 5-10 minutes."
echo ""

read -p "Press Enter to start the fix process..."

echo ""
echo "Step 1: Open Xcode and the Project"
echo "-----------------------------------"
open Fichero.xcodeproj
echo "✅ Xcode should now be opening. Please continue when ready."
read -p "Press Enter when Xcode is open..."

echo ""
echo "Step 2: Check Current Target Configuration"
echo "------------------------------------------"
echo "1. Click on 'Fichero' project at top of Project Navigator"
echo "2. Look at the 'Targets' list in the project editor"
echo "3. Tell me what targets you see (Fichero, FicheroTests, FicheroUITests, etc.)"
echo ""
read -p "What targets do you see? (type them separated by commas): " existing_targets

echo ""
echo "You reported seeing: $existing_targets"
echo ""

# Check if test targets exist
if echo "$existing_targets" | grep -q "FicheroTests"; then
    echo "✅ FicheroTests target exists"
    has_unit_tests=true
else
    echo "❌ FicheroTests target missing - we need to create it"
    has_unit_tests=false
fi

if echo "$existing_targets" | grep -q "FicheroUITests"; then
    echo "✅ FicheroUITests target exists"
    has_ui_tests=true
else
    echo "❌ FicheroUITests target missing - we need to create it"
    has_ui_tests=false
fi

echo ""

# Create test targets if needed
if [ "$has_unit_tests" = false ]; then
    echo "Step 3: Create Unit Test Target"
    echo "-------------------------------"
    echo "1. Go to File > New > Target (Cmd+N)"
    echo "2. Select 'macOS' tab"
    echo "3. Choose 'Test' category"
    echo "4. Select 'Unit Testing Bundle'"
    echo "5. Click 'Next'"
    echo "6. Product Name: FicheroTests"
    echo "7. Language: Swift"
    echo "8. Embed in Application: Fichero (should be selected)"
    echo "9. Click 'Finish'"
    echo "10. Click 'Activate' when prompted"
    echo ""
    read -p "Press Enter when you've created the unit test target..."
fi

if [ "$has_ui_tests" = false ]; then
    echo ""
    echo "Step 4: Create UI Test Target"
    echo "-----------------------------"
    echo "1. Go to File > New > Target (Cmd+N)"
    echo "2. Select 'macOS' tab"
    echo "3. Choose 'Test' category"
    echo "4. Select 'UI Testing Bundle'"
    echo "5. Click 'Next'"
    echo "6. Product Name: FicheroUITests"
    echo "7. Language: Swift"
    echo "8. Embed in Application: Fichero (should be selected)"
    echo "9. Click 'Finish'"
    echo "10. Click 'Activate' when prompted"
    echo ""
    read -p "Press Enter when you've created the UI test target..."
fi

echo ""
echo "Step 5: Configure Test File Target Membership"
echo "---------------------------------------------"
echo "1. In Project Navigator, expand 'FicheroTests' folder"
echo "2. Select ALL files in this folder"
echo "3. Open File Inspector (right panel, blue file icon)"
echo "4. Under 'Target Membership', check:"
echo "   ✅ FicheroTests"
echo "   ❌ Fichero (uncheck main app target)"
echo "5. Repeat for 'FicheroUITests' folder:"
echo "   ✅ FicheroUITests"
echo "   ❌ Fichero (uncheck main app target)"
echo ""
read -p "Press Enter when you've configured target membership..."

echo ""
echo "Step 6: Set Test Host for Test Targets"
echo "--------------------------------------"
echo "1. Select 'FicheroTests' target"
echo "2. Go to 'Build Settings' tab"
echo "3. Search for 'Test Host'"
echo "4. Set 'TEST_HOST' to:"
echo "   $(BUILT_PRODUCTS_DIR)/Fichero.app/Contents/MacOS/Fichero"
echo "5. Repeat for 'FicheroUITests' target"
echo ""
read -p "Press Enter when you've set the test host..."

echo ""
echo "Step 7: Configure Scheme for Testing"
echo "-------------------------------------"
echo "1. Click on the scheme selector (next to run/stop buttons)"
echo "2. Select 'Manage Schemes...'"
echo "3. Click '+' button to add new scheme"
echo "4. Select 'FicheroTests'"
echo "5. Click 'Close'"
echo "6. Select 'FicheroTests' scheme from the dropdown"
echo ""
read -p "Press Enter when you've configured the scheme..."

echo ""
echo "Step 8: Verify Test Configuration"
echo "---------------------------------"
echo "1. Click on the Test Navigator (diamond icon or Cmd+6)"
echo "2. You should now see:"
echo "   - FicheroTests with test methods"
echo "   - FicheroUITests with test methods"
echo "3. Each test method should have a diamond icon (🔷)"
echo ""
read -p "Press Enter when you've verified the test navigator..."

echo ""
echo "Step 9: Run Tests"
echo "----------------"
echo "1. Make sure 'FicheroTests' scheme is selected"
echo "2. Press 'Cmd+U' to run all tests"
echo "3. Or click the diamond icon next to specific tests"
echo ""
echo "You should see:"
echo "  ✅ Tests start running"
echo "  ✅ Green checkmarks for passing tests"
echo "  ✅ Test report showing results"
echo ""
read -p "Press Enter when you've run the tests..."

echo ""
echo "🎉 Complete Fix Applied!"
echo "========================"
echo ""
echo "Summary of what we fixed:"
echo "  ✅ Created test targets (if missing)"
echo "  ✅ Configured target membership"
echo "  ✅ Set test host correctly"
echo "  ✅ Configured scheme for testing"
echo "  ✅ Verified test configuration"
echo ""
echo "The 'Cannot run tests' issue should now be resolved!"
echo ""

echo "🧪 Final Verification"
echo "====================="
echo ""
echo "Let's verify everything is working:"
echo ""

# Check schemes again
echo "Current schemes after fix:"
xcodebuild -list -workspace Fichero.xcodeproj/project.xcworkspace 2>/dev/null | grep -A 10 "Schemes:" || echo "  (Checking...)"
echo ""

echo "If you can now:"
echo "  ✅ See test targets in the scheme selector"
echo "  ✅ See test methods in the test navigator"
echo "  ✅ Run tests with Cmd+U"
echo "  ✅ See test results with green checkmarks"
echo ""
echo "Then the fix was successful! 🎉"
echo ""

echo "📚 Additional Resources"
echo "====================="
echo ""
echo "If you need more help:"
echo "  📄 FIX_XCODE_TESTS_STEP_BY_STEP.md - Visual guide"
echo "  📄 FIX_TESTS_GUIDE.md - Comprehensive guide"
echo "  📄 complete_test_fix.sh - This script"
echo ""
echo "Common issues and solutions:"
echo "  - 'No testable targets': Run this script again"
echo "  - 'Scheme not configured': Check scheme settings"
echo "  - 'Build failed': Clean build folder and retry"
echo ""

echo "Thank you for using Fichero! 🎉"
echo "Your tests should now be fully functional."