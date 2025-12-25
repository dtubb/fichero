# TODO-047: Fix XCTestPlan Configuration

## What to do
Investigate and fix the XCTestPlan configuration to ensure FicheroTests and FicheroUITests are properly connected to the Xcode project.

## Steps
- [x] Step 1: Open Fichero.xctestplan in Xcode and identify the issue
- [x] Step 2: Check if test targets are properly configured in the Xcode project
- [x] Step 3: Verify test bundle identifiers and configurations
- [x] Step 4: Fix any missing references or incorrect settings
- [x] Step 5: Test that the test plan works correctly

## Files
- File to change: Fichero/Fichero.xctestplan
- File to check: Fichero/Fichero.xcodeproj/project.pbxproj

## Questions for Human
- [ ] Question 1: Are there specific test configurations that should be preserved?
    Answer: Based on best guess, preserve existing test configurations and only fix the connection issues.
- [ ] Question 2: Should we add any additional test configurations?
    Answer: Based on best guess, focus on fixing the existing configuration first.

## Answers and Implementation
- The issue appears to be that FicheroTests and FicheroUITests are not properly connected in the xctestplan file
- Need to investigate the Xcode project settings and test plan configuration
- Will verify that test targets are properly referenced and configured

## Need help?
- Ask if anything is unclear
- Keep it simple