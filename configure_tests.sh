#!/bin/bash

echo "🚀 Configuring Xcode Tests for Fichero"
echo "======================================"
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

# Check if test directories exist
echo "🔍 Checking test directories..."
if [ -d "FicheroTests" ]; then
    echo "✅ FicheroTests directory exists"
    TEST_FILES=$(find FicheroTests -name "*.swift" | wc -l)
    echo "   Found $TEST_FILES Swift test files"
else
    echo "❌ FicheroTests directory missing"
fi

if [ -d "FicheroUITests" ]; then
    echo "✅ FicheroUITests directory exists"
    UI_TEST_FILES=$(find FicheroUITests -name "*.swift" | wc -l)
    echo "   Found $UI_TEST_FILES UI test files"
else
    echo "❌ FicheroUITests directory missing"
fi

echo ""
echo "📋 Test Configuration Options"
echo "================================"
echo ""
echo "Option 1: Automatic Configuration (Recommended)"
echo "   This will guide you through adding test targets using Xcode UI"
echo ""
echo "Option 2: Manual Project File Editing (Advanced)"
echo "   This will attempt to modify the project.pbxproj file directly"
echo ""
echo "Option 3: Command Line Testing"
echo "   This will show you how to run tests from command line"
echo ""

read -p "Choose an option (1-3): " option

echo ""

case $option in
    1)
        echo "🎯 Option 1: Automatic Configuration"
        echo "===================================="
        echo ""
        echo "I will now guide you through the process step by step."
        echo "Please follow these instructions in Xcode:"
        echo ""
        
        # Open Xcode
        echo "Step 1: Opening Xcode..."
        open Fichero.xcodeproj
        echo "✅ Xcode should now be opening. Please continue when ready."
        read -p "Press Enter when Xcode is open and you're ready to continue..."
        
        echo ""
        echo "Step 2: Adding Unit Test Target"
        echo "--------------------------------"
        echo "1. Go to File > New > Target (or press Cmd+N)"
        echo "2. Select 'macOS' tab"
        echo "3. Choose 'Test' category"
        echo "4. Select 'Unit Testing Bundle'"
        echo "5. Click 'Next'"
        echo "6. Name: FicheroTests"
        echo "7. Language: Swift"
        echo "8. Embed in Application: Fichero (should be selected)"
        echo "9. Click 'Finish'"
        echo "10. Click 'Activate' when prompted"
        read -p "Press Enter when you've completed this step..."
        
        echo ""
        echo "Step 3: Adding UI Test Target"
        echo "------------------------------"
        echo "1. Go to File > New > Target again (Cmd+N)"
        echo "2. Select 'macOS' tab"
        echo "3. Choose 'Test' category"
        echo "4. Select 'UI Testing Bundle'"
        echo "5. Click 'Next'"
        echo "6. Name: FicheroUITests"
        echo "7. Language: Swift"
        echo "8. Embed in Application: Fichero (should be selected)"
        echo "9. Click 'Finish'"
        echo "10. Click 'Activate' when prompted"
        read -p "Press Enter when you've completed this step..."
        
        echo ""
        echo "Step 4: Configuring Test File Target Membership"
        echo "-----------------------------------------------"
        echo "1. In Project Navigator, expand 'FicheroTests' folder"
        echo "2. Select ALL files in this folder"
        echo "3. Open File Inspector (right panel, blue file icon)"
        echo "4. Under 'Target Membership', check:"
        echo "   ✅ FicheroTests"
        echo "   ❌ Fichero (uncheck main app target)"
        echo "5. Repeat for 'FicheroUITests' folder:"
        echo "   ✅ FicheroUITests"
        echo "   ❌ Fichero (uncheck main app target)"
        read -p "Press Enter when you've completed this step..."
        
        echo ""
        echo "Step 5: Configuring Test Target Dependencies"
        echo "--------------------------------------------"
        echo "1. Click on 'Fichero' project at top of Project Navigator"
        echo "2. Select 'Fichero' target (not the project)"
        echo "3. Go to 'Build Phases' tab"
        echo "4. Under 'Dependencies', add:"
        echo "   - FicheroTests"
        echo "   - FicheroUITests"
        read -p "Press Enter when you've completed this step..."
        
        echo ""
        echo "🎉 Configuration Complete!"
        echo "=========================="
        echo ""
        echo "Your tests should now be properly configured."
        echo ""
        echo "To verify:"
        echo "1. Click on the Test Navigator (diamond icon)"
        echo "2. You should see FicheroTests and FicheroUITests"
        echo "3. Press Cmd+U to run all tests"
        echo ""
        echo "If you see test methods listed, the configuration was successful!"
        ;;
    
    2)
        echo "🔧 Option 2: Manual Project File Editing"
        echo "======================================"
        echo ""
        echo "⚠️  WARNING: This is advanced and can break your project."
        echo "⚠️  A backup has been created: project.pbxproj.backup"
        echo ""
        
        # Create a backup if it doesn't exist
        if [ ! -f "Fichero.xcodeproj/project.pbxproj.backup" ]; then
            cp Fichero.xcodeproj/project.pbxproj Fichero.xcodeproj/project.pbxproj.backup
            echo "✅ Created backup: project.pbxproj.backup"
        fi
        
        echo ""
        echo "I will now attempt to add the test targets to the project file."
        echo "This is complex and may require manual adjustments."
        echo ""
        
        # Check if we can use xcodegen
        if command -v xcodegen &> /dev/null; then
            echo "✅ xcodegen found - we can use it for project generation"
            echo ""
            echo "Creating project.yml for xcodegen..."
            
            # Create a basic project.yml
            cat > project.yml << 'EOF'
name: Fichero
options:
  bundleIdPrefix: com.fichero
  deploymentTarget:
    macOS: 12.0

targets:
  Fichero:
    type: application
    platform: macOS
    sources:
      - path: .
        excludes:
          - "**/FicheroTests/**"
          - "**/FicheroUITests/**"
          - "**/*.xcodeproj"
          - "**/*.xcworkspace"
    settings:
      base:
        PRODUCT_NAME: Fichero
        INFOPLIST_FILE: Fichero/Info.plist

  FicheroTests:
    type: bundle.unit-test
    platform: macOS
    sources:
      - path: FicheroTests
    dependencies:
      - target: Fichero
    settings:
      base:
        PRODUCT_NAME: FicheroTests
        TEST_HOST: "$(BUILT_PRODUCTS_DIR)/Fichero.app/Contents/MacOS/Fichero"

  FicheroUITests:
    type: bundle.ui-test
    platform: macOS
    sources:
      - path: FicheroUITests
    dependencies:
      - target: Fichero
    settings:
      base:
        PRODUCT_NAME: FicheroUITests
        TEST_HOST: "$(BUILT_PRODUCTS_DIR)/Fichero.app/Contents/MacOS/Fichero"
EOF
            
            echo "✅ Created project.yml"
            echo ""
            echo "Now running xcodegen to generate project..."
            xcodegen generate
            
            if [ $? -eq 0 ]; then
                echo "✅ xcodegen completed successfully"
                echo ""
                echo "The project should now have test targets configured."
                echo "Open the project in Xcode and verify the tests appear."
            else
                echo "❌ xcodegen failed"
                echo "Falling back to manual configuration guide..."
                echo ""
                echo "Please follow the manual steps in FIX_XCODE_TESTS_STEP_BY_STEP.md"
            fi
        else
            echo "❌ xcodegen not found"
            echo ""
            echo "Without xcodegen, manual project file editing is very complex."
            echo "I recommend using Option 1 (Automatic Configuration) instead."
            echo ""
            echo "If you still want to proceed with manual editing:"
            echo "1. Open project.pbxproj in a text editor"
            echo "2. Search for 'PBXNativeTarget' section"
            echo "3. Add new target entries for FicheroTests and FicheroUITests"
            echo "4. Add file references in PBXBuildFile section"
            echo "5. Update PBXProject section to include new targets"
            echo ""
            echo "This is error-prone. Consider using Option 1 instead."
        fi
        ;;
    
    3)
        echo "💻 Option 3: Command Line Testing"
        echo "================================"
        echo ""
        echo "You can run tests directly from the command line without"
        echo "configuring test targets in Xcode."
        echo ""
        
        echo "Available test commands:"
        echo ""
        echo "1. List available schemes:"
        echo "   xcodebuild -list -workspace Fichero.xcodeproj/project.xcworkspace"
        echo ""
        echo "2. Run all tests:"
        echo "   xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace \\"
        echo "                  -scheme Fichero -destination 'platform=macOS'"
        echo ""
        echo "3. Run specific test class:"
        echo "   xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace \\"
        echo "                  -scheme Fichero -destination 'platform=macOS' \\"
        echo "                  -only-testing:FicheroTests/SidebarTests"
        echo ""
        echo "4. Run specific test method:"
        echo "   xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace \\"
        echo "                  -scheme Fichero -destination 'platform=macOS' \\"
        echo "                  -only-testing:FicheroTests/SidebarTests/testSidebarViewWithAllDependencies"
        echo ""
        
        read -p "Would you like me to run a test now? (y/n): " run_test
        
        if [ "$run_test" = "y" ] || [ "$run_test" = "Y" ]; then
            echo ""
            echo "🚀 Running tests..."
            echo ""
            
            # Try to run tests
            xcodebuild test -workspace Fichero.xcodeproj/project.xcworkspace -scheme Fichero -destination 'platform=macOS' 2>&1 | head -50
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "✅ Tests completed!"
            else
                echo ""
                echo "⚠️  Tests may have failed or targets may not be configured."
                echo ""
                echo "If you see 'Scheme Fichero is not configured for testing',"
                echo "you need to configure test targets first (use Option 1)."
            fi
        fi
        ;;
    
    *)
        echo "❌ Invalid option selected"
        echo "Please run the script again and choose 1, 2, or 3."
        ;;
esac

echo ""
echo "📚 Additional Resources"
echo "====================="
echo ""
echo "📄 FIX_XCODE_TESTS_STEP_BY_STEP.md - Detailed step-by-step guide"
echo "📄 FIX_TESTS_GUIDE.md - Comprehensive test configuration guide"
echo "📄 project.pbxproj.backup - Backup of original project file"
echo ""
echo "💡 Need help?"
echo "- The step-by-step guide provides visual instructions"
echo "- The comprehensive guide explains all configuration options"
echo "- You can always restore from the backup if needed"
echo ""
echo "Thank you for using Fichero! 🎉"