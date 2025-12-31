# App Layer Audit Report

**Date**: 2025-12-31
**Files Audited**: 3 files (FicheroApp.swift, AppState.swift, ViewSettings.swift)
**Overall Status**: ✅ Good - Minor improvements needed

---

## FicheroApp.swift (351 lines)

### ✅ Strengths

1. **Proper SwiftUI Architecture**
   - Uses modern App/Scene structure
   - Proper @StateObject for app-level state
   - Environment objects correctly injected

2. **Menu Organization**
   - ✅ Commands properly organized
   - ✅ Extracted ViewMenuCommands component
   - ✅ Uses @FocusedValue for document actions
   - ✅ Clean .commands structure

3. **State Management**
   - ✅ @StateObject for appState, viewSettings, libraryManager
   - ✅ @Environment(\.openWindow) correct
   - ✅ Proper initialization in init()

4. **Logging**
   - ✅ Uses OSLog Logger (not NSLog/print)
   - ✅ Proper subsystem and category

5. **AppKit Usage**
   - ✅ Only NSSavePanel (line 296) - NECESSARY (no SwiftUI equivalent)
   - ✅ Import AppKit only for this reason

### ⚠️ Issues Found

**Issue 1: File Organization - LibraryWindow mixed with App**
- **Location**: Lines 140-313 (173 lines)
- **Severity**: Enhancement
- **Problem**: LibraryWindow struct is defined in FicheroApp.swift, making the file larger than needed
- **Fix**: Extract to separate `Views/LibraryWindow.swift` file
- **Benefit**: Cleaner separation, easier to test

**Issue 2: File Organization - WelcomeView mixed with App**
- **Location**: Lines 315-351 (37 lines)
- **Severity**: Enhancement
- **Problem**: WelcomeView struct is defined in FicheroApp.swift
- **Fix**: Extract to separate `Views/Components/WelcomeView.swift` file
- **Benefit**: Reusable component, cleaner organization

**Issue 3: Extra blank line**
- **Location**: Line 148
- **Severity**: Minor
- **Fix**: Remove extra blank line

**Issue 4: Incomplete implementations**
- **Location**: Lines 109-117 (Help menu)
- **Severity**: Documentation
- **Problem**: Commented "// Open help" and "// Check updates"
- **Fix**: Either implement or mark with TODO:

```swift
Button("Fichero Help") {
    // TODO: Implement help documentation
}
```

### 📋 Recommendations

1. **Extract LibraryWindow** to `Views/LibraryWindow.swift`
2. **Extract WelcomeView** to `Views/Components/WelcomeView.swift`
3. **Add TODO comments** for unimplemented features
4. **Remove extra blank line** at 148

### ✅ What's Correct (Keep)

- Menu command organization
- @FocusedValue usage
- StateObject management
- OSLog usage
- NSSavePanel (necessary AppKit)

---

## AppState.swift (124 lines)

### ✅ Strengths

1. **Proper Async Patterns**
   - ✅ Uses async/await correctly
   - ✅ Task {} for async work
   - ✅ @MainActor on class

2. **State Management**
   - ✅ ObservableObject pattern correct
   - ✅ @Published properties appropriate
   - ✅ No business logic (delegates to ProviderService)

3. **Error Handling**
   - ✅ Proper try/catch blocks
   - ✅ Specific URLError handling
   - ✅ User-friendly error messages

4. **Logging**
   - ✅ Uses OSLog Logger
   - ✅ Appropriate log levels (info, error)

### ⚠️ Issues Found

**Issue 1: Missing MARK sections**
- **Location**: Throughout file
- **Severity**: Enhancement
- **Problem**: No MARK comments for organization
- **Fix**: Add MARK sections:

```swift
// MARK: - Properties
@Published var isBackendRunning: Bool = false

// MARK: - Initialization
init() { }

// MARK: - Backend Health
func checkBackendHealth() async { }

// MARK: - Provider Management
func loadProviders() async { }
```

**Issue 2: Empty function implementations**
- **Location**: Lines 112-122
- **Severity**: Warning
- **Problem**: Three functions with no implementation:
  ```swift
  func refreshStats() async {
      // Will call GET /api/stats
  }
  ```
- **Fix**: Either implement or remove. If keeping for future:

```swift
func refreshStats() async {
    // TODO: Implement stats refresh via GET /api/stats
    logger.warning("refreshStats not yet implemented")
}

func startBackend() async {
    // TODO: Launch Python backend: python -m fichero serve
    logger.warning("startBackend not yet implemented")
}

func stopBackend() {
    // TODO: Terminate backend subprocess
    logger.warning("stopBackend not yet implemented")
}
```

**Issue 3: Hardcoded API URL**
- **Location**: Line 40
- **Severity**: Enhancement
- **Problem**: `http://127.0.0.1:8765/api/health` hardcoded
- **Fix**: Extract to configuration:

```swift
// At top of AppState
private enum Config {
    static let apiBaseURL = "http://127.0.0.1:8765"
    static let apiHealthEndpoint = "/api/health"
}

// In checkBackendHealth
guard let url = URL(string: "\(Config.apiBaseURL)\(Config.apiHealthEndpoint)") else {
```

### 📋 Recommendations

1. **Add MARK sections** for better organization
2. **Mark unimplemented functions** with TODO or remove
3. **Extract API configuration** to constants
4. **Consider @AppStorage** for isFirstLaunchProviderSetup persistence

### ✅ What's Correct (Keep)

- @MainActor usage
- ObservableObject pattern
- Async/await patterns
- Error handling
- OSLog usage

---

## ViewSettings.swift (30 lines)

### ✅ Strengths

1. **Clean and Focused**
   - ✅ Single responsibility
   - ✅ Simple observable object
   - ✅ @MainActor correct

2. **State Management**
   - ✅ ObservableObject pattern
   - ✅ @Published properties correct
   - ✅ Good default values

### ⚠️ Issues Found

**Issue 1: LibraryLayout dependency**
- **Location**: Line 22
- **Severity**: Warning
- **Problem**: Comment says "LibraryLayout is defined in LibraryView.swift"
- **Impact**: Creates unnecessary coupling, ViewSettings depends on a View file
- **Fix**: Move LibraryLayout enum to this file or to a Models file:

```swift
/// Library view layout options
enum LibraryLayout: String, CaseIterable {
    case icons
    case list
    case table
    case map
}
```

**Issue 2: No persistence**
- **Location**: Throughout file
- **Severity**: Enhancement
- **Problem**: User preferences don't persist across app launches
- **Fix**: Consider using @AppStorage for persistent settings:

```swift
import SwiftUI

/// Observable settings for view configuration
@MainActor
class ViewSettings: ObservableObject {
    @AppStorage("view.sidebarMode") var sidebarMode: SidebarMode = .navigate
    @AppStorage("view.libraryLayout") var libraryLayout: LibraryLayout = .icons
    @AppStorage("view.previewMode") var previewMode: PreviewMode = .standard
    @AppStorage("view.showInspector") var showInspector: Bool = true
    @AppStorage("view.showQuickLook") var showQuickLook: Bool = false
}
```

**Note**: @AppStorage requires RawRepresentable conformance, so enums need String rawValue (already have it).

**Issue 3: Missing MARK section**
- **Location**: Throughout file
- **Severity**: Minor
- **Problem**: No MARK for Enums section
- **Fix**: Add:

```swift
// MARK: - View Mode Enums

/// Sidebar mode selection
enum SidebarMode: String, CaseIterable { }
```

### 📋 Recommendations

1. **Move LibraryLayout enum** to ViewSettings.swift (or Models/)
2. **Consider @AppStorage** for persistence (user preference)
3. **Add MARK sections** for enums
4. **Add doc comments** to enums explaining usage

### ✅ What's Correct (Keep)

- @MainActor usage
- ObservableObject pattern
- Enum definitions
- Default values

---

## Summary: App Layer

### Overall Assessment: ✅ Good

The App layer follows SwiftUI best practices well. Main improvements needed:
1. Extract LibraryWindow and WelcomeView from FicheroApp.swift
2. Add MARK sections for better organization
3. Move LibraryLayout enum to proper location
4. Consider persistence for ViewSettings

### Issues by Severity

**Critical**: 0
**Warning**: 2
- LibraryLayout coupling in ViewSettings
- Empty function implementations in AppState

**Enhancement**: 5
- Extract LibraryWindow to separate file
- Extract WelcomeView to separate file
- Add MARK sections to AppState
- Consider @AppStorage for ViewSettings
- Extract API configuration constants

**Minor**: 2
- Extra blank line in FicheroApp
- Missing MARK sections in ViewSettings

### SwiftUI Compliance: ✅ 95%

- ✅ Pure SwiftUI (AppKit only for NSSavePanel - necessary)
- ✅ Proper state management patterns
- ✅ @MainActor used correctly
- ✅ Modern App/Scene structure
- ✅ OSLog for logging
- ✅ Menu commands properly organized
- ⚠️ Minor organization improvements needed

---

## Action Items

### High Priority
1. [ ] Move LibraryLayout enum to ViewSettings.swift
2. [ ] Mark unimplemented functions with TODO or implement them

### Medium Priority
3. [ ] Extract LibraryWindow to Views/LibraryWindow.swift
4. [ ] Extract WelcomeView to Views/Components/WelcomeView.swift
5. [ ] Add MARK sections to AppState.swift
6. [ ] Extract API configuration to constants

### Low Priority
7. [ ] Add MARK sections to ViewSettings.swift
8. [ ] Consider @AppStorage for ViewSettings persistence
9. [ ] Remove extra blank line in FicheroApp.swift

---

**Next Step**: Proceed to Views/Menu layer audit (3 files)
