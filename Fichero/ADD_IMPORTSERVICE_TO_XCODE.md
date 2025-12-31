# Add ImportService.swift to Xcode Project

**File Created:** `Fichero/Services/ImportService.swift`
**Status:** File exists on disk but not in Xcode project
**Issue:** Build fails with "cannot find 'ImportService' in scope"

## Steps to Add File in Xcode

1. Open `Fichero.xcodeproj` in Xcode
2. In Project Navigator, navigate to `Fichero` → `Services`
3. Right-click on the `Services` folder
4. Select "Add Files to 'Fichero'..."
5. Navigate to `Fichero/Services/ImportService.swift`
6. Make sure "Copy items if needed" is **UNCHECKED** (file is already in the correct location)
7. Make sure "Add to targets" has **Fichero** checked
8. Click "Add"
9. Build (⌘B) to verify

## After Adding

Once ImportService.swift is added to the project, the following changes in FicheroApp.swift will work:

- Line 8: `@StateObject private var importService = ImportService()`
- Line 19: `.environmentObject(importService)`
- Lines 21-34: `.fileImporter()` modifiers
- Lines 280-324: File and folder import handlers using ImportService

## Why Manual Addition?

The Xcode project file (.xcodeproj) is a complex property list with:
- File UUIDs
- Build phase references
- Target memberships
- Group hierarchies

Programmatic editing risks corruption. Xcode's GUI safely manages all these references.

## Verification

After adding the file:
```bash
cd /Users/dtubb/code/fichero_main/fichero/Fichero
xcodebuild -project Fichero.xcodeproj -scheme Fichero -configuration Debug build
```

Should build successfully.
