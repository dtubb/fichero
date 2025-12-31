# SwiftUI Audit & Remediation Plan

**Date:** 2025-12-30
**Status:** Ready for Implementation
**Priority:** P0 (Critical - Must be fixed before production)

## Executive Summary

Comprehensive audit of the Fichero macOS app revealed **critical violations** of the SwiftUI-only architecture principle. Multiple files use AppKit APIs, anti-patterns, and fail SwiftLint checks. This plan outlines all issues and remediation steps.

---

## 🚨 Critical Issues Found

### 1. AppKit Usage Violations

| File | Line(s) | Violation | Impact | Fix Required |
|------|---------|-----------|--------|--------------|
| `FicheroApp.swift` | 253-276 | NSOpenPanel for file import | HIGH | Replace with `.fileImporter()` modifier |
| `ErrorService.swift` | 3, 199-259 | NSAlert, NSApp.keyWindow | HIGH | Replace with SwiftUI `.alert()` modifier |
| `CacheModel.swift` | 2, 10, 22, 24-31, 96-108 | NSCache, NSImage, NSView | MEDIUM | Use SwiftUI Image caching |
| `ProviderLogoView.swift` | 11 | NSImage(named:) | LOW | Use Image() directly |
| `EditorView.swift` | 2-3 | Quartz, PDFKit imports | LOW | Evaluate necessity (PDF viewing may require) |

### 2. Anti-Pattern Violations

| File | Line(s) | Anti-Pattern | Fix Required |
|------|---------|--------------|--------------|
| `ErrorService.swift` | 167, 198, 227, 251, 271 | DispatchQueue.main.async | Use @MainActor methods |
| `CacheModel.swift` | 69-75, 89 | NotificationCenter | Replace with SwiftUI state management |
| `ChatView.swift` | 73 | NSLog | Replace with OSLog |
| `AppState.swift` | 66, 74, 78, 94 | NSLog | Replace with OSLog |

### 3. Task Cancellation Issues

10 files use `.task {}` blocks - need to verify ALL check `Task.isCancelled`:

- AddProviderSheet.swift
- AIModelSelectionView.swift
- ProvidersView.swift
- ChatView.swift
- ChatInspector.swift
- ContentView.swift
- WorkflowInspector.swift
- SidebarItemRow.swift
- SidebarViewExtensions.swift
- NodePopover.swift

### 4. SwiftLint Violations (100+ warnings)

**Categories:**
- Trailing whitespace (60+ instances)
- Missing trailing newlines (10+ files)
- Implicit optional initialization (7 instances)
- Line length violations (2 instances)
- Unused closure parameters (3 instances)

**Most Affected Files:**
- WorkflowStore.swift (21 violations)
- CacheModel.swift (21 violations)
- SidebarState.swift (15 violations)
- DragDropModel.swift (13 violations)
- WorkflowTypes.swift (3 violations)

---

## ✅ Good Practices Found

**The codebase does many things correctly:**

1. ✅ Extensive use of `@MainActor` on services (18 instances)
2. ✅ Good use of `@ViewBuilder` (31 instances across 10 files)
3. ✅ Proper state management with `@Published`, `@State`, `@StateObject`
4. ✅ OSLog usage in most places (Logger with subsystem/category)
5. ✅ Proper dependency injection with `@EnvironmentObject`
6. ✅ Cache management in SidebarView (lines 26-50)
7. ✅ FocusedValue pattern for menu commands (FocusedCommandButtons.swift)
8. ✅ NavigationSplitView for 3-column layout
9. ✅ Structured file organization (App/, Models/, Services/, Views/)

---

## 🔧 Detailed Remediation Steps

### Phase 1: Critical AppKit Removals (P0)

#### 1.1 FicheroApp.swift - Replace NSOpenPanel

**Current Code (lines 252-277):**
```swift
private func importFiles() {
    let panel = NSOpenPanel()
    panel.allowsMultipleSelection = true
    panel.canChooseDirectories = false
    panel.canChooseFiles = true
    panel.allowedContentTypes = [.image, .pdf, .plainText]

    if panel.runModal() == .OK {
        for url in panel.urls {
            print("Import file: \(url.path)")
        }
    }
}
```

**SwiftUI Solution:**
```swift
// Add state to FicheroApp
@State private var showingFileImporter = false
@State private var showingFolderImporter = false

// Replace import methods with simple state toggles
private func importFiles() {
    showingFileImporter = true
}

private func importFolder() {
    showingFolderImporter = true
}

// In body, after .environmentObject():
.fileImporter(
    isPresented: $showingFileImporter,
    allowedContentTypes: [.image, .pdf, .plainText],
    allowsMultipleSelection: true
) { result in
    switch result {
    case .success(let urls):
        for url in urls {
            // Import logic here
            print("Import file: \(url.path)")
        }
    case .failure(let error):
        print("File import failed: \(error)")
    }
}
.fileImporter(
    isPresented: $showingFolderImporter,
    allowedContentTypes: [.folder],
    allowsMultipleSelection: false
) { result in
    // Folder import logic
}
```

#### 1.2 ErrorService.swift - Replace NSAlert with SwiftUI Alert

**Problem:** Uses NSAlert, NSApp.keyWindow, DispatchQueue.main.async

**Solution Strategy:**
1. Create `@Published var currentAlert: ErrorAlertModel?` in ErrorService
2. Use SwiftUI `.alert()` modifier in ContentView to show alerts
3. Remove all NSAlert code and DispatchQueue.main.async
4. Use @MainActor for methods that update @Published properties

**New ErrorAlertModel:**
```swift
struct ErrorAlertModel: Identifiable {
    let id = UUID()
    let errorModel: ErrorModel
    let showRetry: Bool
}
```

**ErrorService changes:**
```swift
@MainActor
class ErrorService: ObservableObject {
    @Published var currentAlert: ErrorAlertModel?

    // Remove import AppKit
    // Remove NSAlert methods

    @MainActor
    private func showUserFeedback(for errorModel: ErrorModel) {
        currentAlert = ErrorAlertModel(
            errorModel: errorModel,
            showRetry: errorModel.isRecoverable
        )
    }
}
```

**ContentView integration:**
```swift
.alert(item: $errorService.currentAlert) { alertModel in
    Alert(
        title: Text(alertModel.errorModel.title),
        message: Text(alertModel.errorModel.message),
        primaryButton: .default(Text("OK")),
        secondaryButton: alertModel.showRetry ?
            .default(Text("Retry")) { /* retry logic */ } : nil
    )
}
```

#### 1.3 CacheModel.swift - Remove AppKit Dependencies

**Problems:**
- Uses NSCache, NSImage, NSView
- Uses NotificationCenter for memory management
- Unnecessary complexity for SwiftUI

**Solution:**
1. Remove AppKit-based icon caching (SwiftUI caches Images automatically)
2. Remove NotificationCenter memory observation
3. Keep only lightweight data caching if needed
4. OR: Delete entire file if not providing value

**Simplified CacheModel (if needed):**
```swift
import SwiftUI

@MainActor
class CacheModel: ObservableObject {
    // Simple in-memory cache for computed data
    private var dataCache: [String: Any] = [:]

    func cache<T>(_ value: T, forKey key: String) {
        dataCache[key] = value
    }

    func getCached<T>(forKey key: String) -> T? {
        return dataCache[key] as? T
    }

    func clear() {
        dataCache.removeAll()
    }
}
```

**Note:** SwiftUI already caches `Image(systemName:)` efficiently. Custom caching is usually unnecessary.

#### 1.4 ProviderLogoView.swift - Remove NSImage

**Current Code (lines 10-15):**
```swift
if let logoAsset = entry.logoAsset,
   let nsImage = NSImage(named: logoAsset) {
    Image(nsImage: nsImage)
        .resizable()
        .aspectRatio(contentMode: .fit)
}
```

**SwiftUI Solution:**
```swift
if let logoAsset = entry.logoAsset {
    Image(logoAsset)  // SwiftUI Image loads from asset catalog directly
        .resizable()
        .aspectRatio(contentMode: .fit)
}
```

---

### Phase 2: Anti-Pattern Fixes (P1)

#### 2.1 Replace DispatchQueue.main with @MainActor

**Files to fix:**
- ErrorService.swift (multiple instances)
- Any other files found during implementation

**Pattern to replace:**
```swift
// ❌ OLD
DispatchQueue.main.async {
    self.property = newValue
}

// ✅ NEW
@MainActor
func updateProperty(_ newValue: Type) {
    self.property = newValue
}
```

#### 2.2 Replace NSLog with OSLog

**Files to fix:**
- ChatView.swift:73
- AppState.swift:66, 74, 78, 94

**Pattern:**
```swift
// Add at top of file
import OSLog

extension Logger {
    static let chat = Logger(subsystem: "ca.tubb.Fichero", category: "chat")
    static let app = Logger(subsystem: "ca.tubb.Fichero", category: "app")
}

// Replace NSLog with:
Logger.chat.info("User message: \(message)")
Logger.app.error("Failed to load: \(error.localizedDescription)")
```

---

### Phase 3: Task Cancellation Verification (P1)

**Check all `.task {}` blocks for cancellation handling:**

```swift
// ❌ BAD - No cancellation check
.task {
    await longRunningOperation()
}

// ✅ GOOD - Checks cancellation
.task {
    guard !Task.isCancelled else { return }
    await longRunningOperation()

    guard !Task.isCancelled else { return }
    await anotherOperation()
}

// ✅ BETTER - Structured concurrency
.task {
    await withTaskCancellationHandler {
        await longRunningOperation()
    } onCancel: {
        // Cleanup logic
    }
}
```

**Files to audit:** (10 files listed in section 3 above)

---

### Phase 4: SwiftLint Cleanup (P2)

#### 4.1 Automated Fixes

Run SwiftLint autocorrect:
```bash
cd Fichero && swiftlint --fix Fichero/
```

This will automatically fix:
- Trailing whitespace
- Trailing newlines
- Some formatting issues

#### 4.2 Manual Fixes

**Implicit Optional Initialization:**
```swift
// ❌ OLD
var selectedId: String? = nil

// ✅ NEW
var selectedId: String?
```

**Unused Closure Parameters:**
```swift
// ❌ OLD
.map { item in item.name }

// ✅ NEW
.map { $0.name }
```

**Line Length:**
- Break long lines at logical points
- Max 120 characters per line

---

## 📋 Implementation Checklist

### Pre-Implementation
- [ ] Create feature branch: `fix/swiftui-audit-2025-12-30`
- [ ] Backup current working state
- [ ] Run baseline build: `xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero`
- [ ] Run baseline SwiftLint: `swiftlint lint Fichero/ > swiftlint-before.txt`

### Phase 1: Critical AppKit Removals
- [ ] Fix FicheroApp.swift NSOpenPanel → fileImporter
- [ ] Fix ErrorService.swift NSAlert → SwiftUI Alert
- [ ] Fix CacheModel.swift AppKit dependencies
- [ ] Fix ProviderLogoView.swift NSImage usage
- [ ] Build and test after each file
- [ ] Verify file import/export still works

### Phase 2: Anti-Pattern Fixes
- [ ] Replace all DispatchQueue.main with @MainActor
- [ ] Replace all NSLog with OSLog
- [ ] Verify all ObservableObject classes are @MainActor
- [ ] Test state updates work correctly

### Phase 3: Task Cancellation
- [ ] Audit all 10 .task {} blocks
- [ ] Add cancellation checks where missing
- [ ] Test view dismissal scenarios
- [ ] Verify no memory leaks from uncancelled tasks

### Phase 4: SwiftLint Cleanup
- [ ] Run `swiftlint --fix Fichero/`
- [ ] Fix remaining manual violations
- [ ] Run `swiftlint lint Fichero/` - expect 0 warnings
- [ ] Save final report: `swiftlint lint Fichero/ > swiftlint-after.txt`

### Final Verification
- [ ] Full clean build: `xcodebuild clean build -project Fichero/Fichero.xcodeproj -scheme Fichero`
- [ ] Run all tests: `xcodebuild test -project Fichero/Fichero.xcodeproj -scheme Fichero`
- [ ] Manual smoke testing:
  - [ ] File import works
  - [ ] Folder import works
  - [ ] Error dialogs appear
  - [ ] Provider logos display
  - [ ] Chat view functions
  - [ ] Workflow view functions
- [ ] Code review against SWIFTUI_PRINCIPLES.md checklist
- [ ] Commit with detailed message
- [ ] Create PR with this plan as description

---

## 🎯 Success Criteria

1. ✅ **Zero AppKit usage** (except unavoidable system integrations)
2. ✅ **Zero SwiftLint warnings**
3. ✅ **Zero DispatchQueue.main.async** (all @MainActor)
4. ✅ **Zero NotificationCenter** (all SwiftUI state)
5. ✅ **Zero NSLog** (all OSLog)
6. ✅ **All .task blocks handle cancellation**
7. ✅ **Clean xcodebuild** (no errors, no warnings)
8. ✅ **All features still work** (import, export, chat, workflows)

---

## 📊 Estimated Impact

| Category | Files Affected | Lines Changed | Risk Level |
|----------|---------------|---------------|------------|
| AppKit Removal | 5 | ~150 | MEDIUM |
| Anti-Patterns | 4 | ~50 | LOW |
| Task Cancellation | 10 | ~20 | LOW |
| SwiftLint | 20+ | ~100 | LOW |
| **TOTAL** | **30+** | **~320** | **MEDIUM** |

**Time Estimate:** 4-6 hours for careful implementation and testing

---

## 🔍 Code Review Checklist

Before marking complete, verify:

- [ ] No `import AppKit` (except EditorView.swift if needed for PDFKit)
- [ ] No `NSView`, `NSImage`, `NSColor`, `NSFont`
- [ ] No `NSOpenPanel`, `NSSavePanel`, `NSAlert`
- [ ] No `NotificationCenter.default`
- [ ] No `DispatchQueue.main.async`
- [ ] No `NSLog` or `print` statements
- [ ] All ObservableObject classes are `@MainActor`
- [ ] All .task blocks check `Task.isCancelled`
- [ ] All computed view properties use `@ViewBuilder`
- [ ] All view files < 500 lines (split if needed)
- [ ] SwiftLint reports 0 warnings
- [ ] Xcodebuild completes with 0 warnings

---

## 📚 References

- `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md` - Mandatory guidelines
- `CLAUDE.md` - Project architecture and commands
- Apple SwiftUI Documentation (via Sosumi MCP)
- Swift Language Reference (via Ref MCP)

---

## 🚀 Next Steps

1. **Review this plan** with team/user
2. **Create feature branch**
3. **Execute Phase 1** (critical fixes first)
4. **Test thoroughly** after each phase
5. **Document any deviations** from this plan
6. **Update SWIFTUI_PRINCIPLES.md** with lessons learned

---

**Plan Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** Ready for execution
