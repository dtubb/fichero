# SwiftUI Architecture Review - Fichero Frontend

**Review Date:** 2026-02-12  
**Reviewer:** Agent 1 - SwiftUI Architecture Specialist  
**Scope:** All Swift view files in `Fichero/Views/`  
**Reference:** `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`

---

## Executive Summary

**Overall Status:** ⚠️ **CRITICAL VIOLATIONS FOUND**

### Critical Issues Summary
- **6 files** with extensive AppKit usage (NSViewRepresentable, NSView subclasses)
- **1 file** with NotificationCenter usage (line 328)
- **3 files** with services created in views (@StateObject for services)
- **1 file** exceeds 1000 lines (1035 lines)
- **1 file** exceeds recommended 400 lines (1025 lines)

### Compliance Rate
- **Pure SwiftUI:** 107/113 files (94.7%)
- **AppKit violations:** 6/113 files (5.3%)
- **State management violations:** 3/113 files (2.7%)

---

## 🔴 CRITICAL VIOLATIONS

### 1. Extensive AppKit Integration in Image Viewer

**File:** `Fichero/Views/Library/ImageViewerComponents.swift`  
**Size:** 1035 lines ⚠️ (exceeds 1000-line absolute maximum)  
**Severity:** CRITICAL

#### Issues

**Lines 2, 290-671:** Complete NSViewRepresentable implementation with NSScrollView
```swift
import AppKit  // Line 2

struct ImageWithCursorTracking: NSViewRepresentable {  // Line 290
    func makeNSView(context: Context) -> NSScrollView { ... }  // Line 306
    func updateNSView(_ scrollView: NSScrollView, context: Context) { ... }  // Line 401
}
```

**Lines 671-1034:** Extensive NSImageView subclass (364 lines of AppKit code)
```swift
class TrackingImageView: NSImageView {  // Line 671
    // Complex mouse tracking, drag/drop, magnification gestures
    // Drawing code using NSBezierPath, NSGraphicsContext
}
```

**Lines 28, 197, 207, 364, 432, 458, 477:** NSImage usage throughout
```swift
@State private var image: NSImage?  // Line 28
image = NSImage(contentsOf: url)    // Lines 197, 207, 364, 432
```

**Lines 383-388:** NotificationCenter for bounds change observation
```swift
NotificationCenter.default.addObserver(
    context.coordinator,
    selector: #selector(Coordinator.boundsDidChange(_:)),
    name: NSView.boundsDidChangeNotification,
    object: scrollView.contentView
)
```

**Lines 923, 933, 950, 956, 974-975, 991, 1015, 1019-1020:** Direct NSColor, NSFont usage in drawing
```swift
shadow.shadowColor = NSColor.black.withAlphaComponent(0.5)  // Line 923
NSColor.white.setFill()  // Line 933
.font: NSFont.systemFont(ofSize: 9, weight: .medium)  // Line 974
```

#### Root Cause
This file implements a custom image viewer with advanced features (loupe magnification, cursor tracking, pinch-to-zoom) that **currently have no SwiftUI equivalents**. However, the implementation violates the 100% SwiftUI mandate.

#### Recommended Fix
**Priority:** P0 - Must be resolved immediately

**Option 1: Research Native SwiftUI Solutions (PREFERRED)**
1. Use `sosumi.searchAppleDocumentation("SwiftUI magnification gesture")`
2. Investigate `MagnifyGesture`, `SpatialTapGesture` in SwiftUI
3. Check if iOS 17+ / macOS 14+ has new APIs for loupe/magnifier
4. Replace NSScrollView with ScrollView + `.scrollIndicators()` + `.scrollPosition()`

**Option 2: Document Why AppKit is Unavoidable**
If truly unavoidable after exhaustive research:
1. Create `ai/contexts/frontend/appkit_exceptions.md` documenting:
   - Why SwiftUI cannot provide this functionality
   - What APIs were investigated
   - Sosumi search queries performed
2. Extract AppKit code to isolated `ImageViewerAppKitBridge.swift`
3. Keep surface area minimal - wrap in thin SwiftUI view
4. Add inline comments: `// EXCEPTION: No SwiftUI equivalent for custom loupe with NSGraphicsContext drawing`

**Option 3: Simplify Feature Set**
- Remove custom loupe (use system magnifier APIs if available)
- Use standard SwiftUI ScrollView with `.magnification()` modifier
- Accept reduced functionality for 100% SwiftUI compliance

**File Size Fix:**
- Split into 3 files:
  - `ZoomableImagePreview.swift` (~300 lines)
  - `ImageViewerAppKitBridge.swift` (~400 lines) - if AppKit remains
  - `ImageCursorTracking.swift` (~300 lines)

---

### 2. AppKit Magnifier Panel

**File:** `Fichero/Views/Library/MagnifierPanel.swift`  
**Size:** 278 lines  
**Severity:** CRITICAL

#### Issues

**Lines 2, 7, 179-277:** Complete NSViewRepresentable + NSView subclass
```swift
import AppKit  // Line 2

let image: NSImage  // Line 7

struct MagnifierPanelContent: NSViewRepresentable {  // Line 179
    func makeNSView(context: Context) -> NSView { ... }  // Line 186
}

class MagnifierPanelNSView: NSView {  // Line 209
    var image: NSImage?  // Line 210
    // Custom drawing with image.draw(in:from:operation:fraction:)
}
```

**Lines 169-172:** NSCursor manipulation
```swift
.onHover { hovering in
    if hovering {
        NSCursor.resizeUpDown.push()  // Line 169
    } else {
        NSCursor.pop()  // Line 171
    }
}
```

**Lines 189:** NSColor usage
```swift
view.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor  // Line 189
```

#### Recommended Fix
**Priority:** P0

1. **Research SwiftUI alternatives:**
   - `sosumi.searchAppleDocumentation("SwiftUI custom cursor")`
   - Check `.cursor()` modifier availability in macOS 14+
   - Investigate Canvas API for custom drawing: `Canvas { context, size in ... }`

2. **Canvas-based solution (likely viable):**
```swift
Canvas { context, size in
    // Use SwiftUI's Canvas drawing primitives
    let sourceRect = CGRect(...)
    context.draw(Image(nsImage: image), in: rect)  // May still need bridge
}
```

3. **If AppKit truly required:**
   - Document in `appkit_exceptions.md`
   - Reduce to minimal bridge wrapper
   - Isolate in `MagnifierAppKitBridge.swift`

---

### 3. Scroll Wheel Zoom AppKit Bridge

**File:** `Fichero/Views/Library/ScrollWheelZoom.swift`  
**Size:** 36 lines  
**Severity:** HIGH

#### Issues

**Lines 2, 6-35:** Complete NSView subclass for scroll wheel capture
```swift
import AppKit  // Line 2

struct ScrollWheelZoomView: NSViewRepresentable {  // Line 6
    func makeNSView(context: Context) -> NSView { ... }  // Line 11
}

class ScrollWheelCaptureView: NSView {  // Line 23
    override func scrollWheel(with event: NSEvent) { ... }  // Line 26
}
```

#### Recommended Fix
**Priority:** P0

**SwiftUI Native Solution (LIKELY EXISTS):**
```swift
// Check if this already works in SwiftUI:
ScrollView {
    imageContent
}
.gesture(
    MagnifyGesture()
        .onChanged { value in
            scale *= value.magnification
        }
)
```

1. Search: `sosumi.searchAppleDocumentation("SwiftUI scroll wheel gesture")`
2. Test `.onScroll` modifier (macOS 14+)
3. Use `.gesture(MagnifyGesture())` for pinch-to-zoom

**If truly unavoidable:**
- This is a 36-line file - keep as-is but document why in comments
- Add: `// EXCEPTION: SwiftUI has no scroll wheel delta API as of macOS 13`

---

### 4. QuickLook AppKit Integration

**File:** `Fichero/Views/Library/QuickLookComponents.swift`  
**Size:** 363 lines  
**Severity:** HIGH

#### Issues

**Lines 3, 322-362:** NSView wrapper for QLPreviewView
```swift
import AppKit  // Line 3

struct QuickLookPreviewView: NSViewRepresentable {  // Line 322
    func makeNSView(context: Context) -> NSView {
        let previewView = QLPreviewView(frame: .zero, style: .normal)!  // Line 326
        let container = NSView()  // Line 331
        // ...
    }
}
```

#### Recommended Fix
**Priority:** P1

**EXCEPTION JUSTIFIED:** QuickLook (QLPreviewView) is an AppKit-only API with no SwiftUI equivalent.

**Actions:**
1. ✅ Keep this AppKit bridge - it's unavoidable
2. Add documentation:
```swift
// EXCEPTION: QLPreviewView is AppKit-only, no SwiftUI equivalent
// Apple has not provided SwiftUI QuickLook preview API as of macOS 14
// Ref: https://developer.apple.com/documentation/quartz/qlpreviewview
```
3. Rename to `QuickLookAppKitBridge.swift` to make AppKit usage explicit
4. Minimize surface area - keep wrapper as thin as possible (already well done)

---

### 5. NotificationCenter Usage in ContentView

**File:** `Fichero/Views/ContentView.swift`  
**Size:** 370 lines  
**Severity:** CRITICAL ⚠️

#### Issue

**Line 328:** NotificationCenter for app termination
```swift
.onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
    // Auto-save workflow when app quits
    if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
        let workflowToSave = editingWorkflow
        Task { @MainActor in
            await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
        }
    }
}
```

#### Why This Violates Principles
Per `SWIFTUI_PRINCIPLES.md`:
- ❌ NotificationCenter is AppKit/UIKit legacy pattern
- ✅ Use `@FocusedValue` for menu commands
- ✅ Use `.onDisappear`, `.task`, or `@Environment(\.scenePhase)` for lifecycle

#### Recommended Fix
**Priority:** P0 - Must fix immediately

**Correct SwiftUI Pattern:**
```swift
@Environment(\.scenePhase) private var scenePhase

// Replace .onReceive with:
.onChange(of: scenePhase) { oldPhase, newPhase in
    if newPhase == .background {
        // Auto-save workflow when app goes to background
        if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
            let workflowToSave = editingWorkflow
            Task { @MainActor in
                await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
            }
        }
    }
}
```

**Alternative (if termination-specific save needed):**
Move save logic to `FicheroApp.swift` and use `@NSApplicationDelegateAdaptor`:
```swift
// In FicheroApp.swift
@NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillTerminate(_ notification: Notification) {
        // Trigger save via @EnvironmentObject or Notification (one-time exception)
    }
}
```

---

### 6. NSImage Usage in Activity and Workflow Views

**Files:**
- `Fichero/Views/Activity/ActivityDiagramView.swift` (Lines 11, 53, 134)
- `Fichero/Views/Workflow/WorkflowEditor.swift` (Lines 36, 773, 945)

**Severity:** MEDIUM

#### Issues

**ActivityDiagramView.swift:**
```swift
@State private var diagramImage: NSImage?  // Line 11

private func diagramContent(_ image: NSImage) -> some View {  // Line 53
    Image(nsImage: image)  // Line 55 - OK bridge point
}

if let image = NSImage(data: data) {  // Line 134
    diagramImage = image
}
```

**WorkflowEditor.swift:**
```swift
@State private var diagramImage: NSImage?  // Lines 36, 773

diagramImage = NSImage(data: data)  // Line 945
```

#### Why This is Acceptable (but improvable)
- ✅ Using NSImage only as data holder
- ✅ Converting to SwiftUI `Image(nsImage:)` for display
- ⚠️ Could use `UIImage` or platform-agnostic `Image` type

#### Recommended Fix
**Priority:** P2 (Low priority - not a violation, just optimization)

**Option 1: Keep as-is** (current approach is fine)
- NSImage → Image bridge is acceptable
- Clear separation between data loading (AppKit) and display (SwiftUI)

**Option 2: Use SwiftUI Image type**
```swift
@State private var diagramImage: Image?

// When loading:
if let nsImage = NSImage(data: data) {
    diagramImage = Image(nsImage: nsImage)
}
```

**No action required** - this is not a violation of SwiftUI principles.

---

## ⚠️ HIGH PRIORITY ISSUES

### 7. Services Created in Views (@StateObject pattern violation)

**Severity:** HIGH  
**Impact:** Memory leaks, multiple service instances, broken dependency injection

#### File 1: IntegrationsView.swift

**Line 6:**
```swift
@StateObject private var service = IntegrationsService()
```

**Problem:**
- Service should be injected via `@EnvironmentObject`, not created in view
- Each view instance creates a new service (wasteful)
- Cannot be shared across app
- Violates single responsibility principle

**Fix:**
```swift
// In view:
@EnvironmentObject var integrationsService: IntegrationsService

// In FicheroApp.swift or parent view:
.environmentObject(IntegrationsService())
```

---

#### File 2: ModelComparisonView.swift

**Line 6:**
```swift
@StateObject private var service = ModelComparisonService()
```

**Same issues as above.**

**Fix:**
```swift
@EnvironmentObject var modelComparisonService: ModelComparisonService
```

---

#### File 3: WorkflowExecutionView.swift

**Line 9:**
```swift
@StateObject private var executionService = WorkflowExecutionService()
```

**Same issues as above.**

**Fix:**
```swift
@EnvironmentObject var workflowExecutionService: WorkflowExecutionService

// Note line 18: Service DOES receive library path properly
// Just needs to be injected instead of created
```

---

### 8. File Size Violations

#### Critical: ImageViewerComponents.swift
- **Size:** 1035 lines
- **Limit:** 1000 lines (absolute maximum)
- **Overage:** +35 lines (3.5%)
- **Recommended:** Split into 3 files

#### High Priority: WorkflowEditor.swift
- **Size:** 1025 lines
- **Recommended limit:** 400 lines
- **Overage:** +625 lines (156%)
- **Note:** File has comment acknowledging this (lines 8-9)
- **SwiftLint disabled:** Lines 4, 13 (`file_length`, `type_body_length`)

**Recommended refactoring:**
```
WorkflowEditor.swift (200 lines) - Main view structure
WorkflowEditor+Canvas.swift (300 lines) - Canvas interactions
WorkflowEditor+Execution.swift (250 lines) - Run/execution logic
WorkflowEditor+Diagram.swift (150 lines) - Diagram preview
WorkflowEditor+Helpers.swift (125 lines) - Utilities
```

---

## ✅ GOOD PATTERNS OBSERVED

### 1. Excellent @FocusedValue Usage
**Files:** 5 files use @FocusedValue correctly for menu commands
- `Menu/ImagePreviewMenuCommands.swift`
- `Menu/FocusedCommandButtons.swift`
- `Menu/ViewMenuCommands.swift`
- `Sidebar/SidebarView.swift`
- `Sidebar/SidebarViewExtensions.swift`

**Example from ContentView.swift (Line 242):**
```swift
.focusedSceneValue(\.imageZoomActions, ImageZoomActions(
    zoomIn: zoomIn,
    zoomOut: zoomOut,
    actualSize: actualSize,
    zoomToFit: fitToWindow,
    canZoomIn: scale < maxScale,
    canZoomOut: scale > minScale,
    currentScale: scale
))
```

**✅ This is the CORRECT SwiftUI pattern** - no NotificationCenter needed!

---

### 2. Proper @EnvironmentObject Usage
**Examples:**
- ContentView.swift: Lines 19-27 (8 environment objects injected)
- WorkflowEditor.swift: Lines 43-47 (5 services injected)
- QuickLookComponents.swift: Line 19 (APIClient injected)

**✅ Correct dependency injection pattern**

---

### 3. @ViewBuilder on Computed Properties
**Good examples found:**
- EditorView.swift: Lines 22, 70 (`@ViewBuilder private func`)
- ActivityDiagramView.swift: Lines 52, 63, 81 (`@ViewBuilder private func/var`)

**✅ Follows best practices** for view composition

---

### 4. Proper Task Cancellation Checking
**Examples:**
- WorkflowExecutionView.swift: Line 16
```swift
.task {
    guard !Task.isCancelled else { return }
    // ...
}
```

**✅ Prevents work after view disappears**

---

## 📊 METRICS SUMMARY

### File Size Distribution
| Category | Count | Percentage |
|----------|-------|------------|
| < 200 lines | 78 | 69.0% |
| 200-400 lines | 29 | 25.7% |
| 400-1000 lines | 4 | 3.5% |
| > 1000 lines | 2 | 1.8% |

### AppKit Usage by File
| File | Lines of AppKit Code | % of File |
|------|---------------------|-----------|
| ImageViewerComponents.swift | ~600 | 58% |
| MagnifierPanel.swift | ~150 | 54% |
| ScrollWheelZoom.swift | 36 | 100% |
| QuickLookComponents.swift | 40 | 11% |

### State Management
| Pattern | Count | Status |
|---------|-------|--------|
| @EnvironmentObject (services) | 85 | ✅ Correct |
| @StateObject (view models) | 11 | ✅ Correct |
| @StateObject (services) | 3 | ❌ Wrong |
| @State (local state) | 200+ | ✅ Correct |

---

## 🎯 ACTION PLAN

### Phase 1: Critical Fixes (Complete within 1 week)

**Priority 0 - Immediate:**
1. ✅ Fix NotificationCenter in ContentView.swift (Line 328)
   - Replace with `@Environment(\.scenePhase)`
   - **Estimated time:** 30 minutes

2. 🔍 Research SwiftUI alternatives for ImageViewerComponents.swift
   - Run: `sosumi.searchAppleDocumentation("SwiftUI magnification loupe")`
   - Run: `sosumi.searchAppleDocumentation("SwiftUI scroll view magnify")`
   - Run: `sosumi.searchAppleDocumentation("Canvas drawing image")`
   - **Estimated time:** 4 hours research

3. 🔍 Research SwiftUI alternatives for ScrollWheelZoom.swift
   - Run: `sosumi.searchAppleDocumentation("SwiftUI scroll wheel")`
   - Test `.gesture(MagnifyGesture())`
   - **Estimated time:** 2 hours

4. ⚠️ Fix service injection in 3 files
   - IntegrationsView.swift
   - ModelComparisonView.swift
   - WorkflowExecutionView.swift
   - **Estimated time:** 2 hours

---

### Phase 2: AppKit Documentation (If unavoidable after research)

**If SwiftUI alternatives don't exist:**
1. Create `ai/contexts/frontend/appkit_exceptions.md`
2. Document each exception with:
   - Feature description
   - Why SwiftUI cannot provide it
   - Sosumi search queries performed
   - Alternative approaches considered
3. Add inline comments to each AppKit usage point
4. Extract to isolated bridge files

**Estimated time:** 4 hours

---

### Phase 3: File Size Refactoring (2-3 weeks)

1. Split ImageViewerComponents.swift (1035 lines → 3 files)
2. Split WorkflowEditor.swift (1025 lines → 5 files)
3. Consider splitting other 400+ line files

**Estimated time:** 16 hours

---

## 📋 COMPLIANCE CHECKLIST

Per `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`:

| Requirement | Status | Notes |
|------------|--------|-------|
| ❌ 100% SwiftUI, NO AppKit | **FAIL** | 6 files use AppKit (5.3%) |
| ✅ Check Sosumi before AppKit | **N/A** | Will do in Phase 1 |
| ✅ Use @FocusedValue for menu commands | **PASS** | 5 files use correctly |
| ❌ NO NotificationCenter | **FAIL** | 1 usage in ContentView.swift |
| ⚠️ Cache expensive work | **WARN** | Some view rebuilds not optimized |
| ✅ Handle cancellation in .task | **PASS** | Good usage seen |
| ⚠️ Files < 400 lines | **WARN** | 6 files exceed limit |
| ✅ @ViewBuilder on computed views | **PASS** | Used correctly |
| ✅ @MainActor for UI updates | **PASS** | Good usage throughout |
| ✅ OSLog for logging | **PASS** | Used consistently |
| ⚠️ Services as @EnvironmentObject | **WARN** | 3 violations |

**Overall Grade: C (70%)**
- Core patterns are good
- AppKit usage is the primary issue
- File sizes need attention
- NotificationCenter must be removed

---

## 📝 NEXT STEPS

1. **Immediate:** Fix NotificationCenter in ContentView.swift
2. **This week:** Research SwiftUI alternatives for all AppKit usage
3. **Next week:** Fix service injection violations
4. **Next sprint:** File splitting and refactoring

---

## 🔗 REFERENCES

- SwiftUI Principles: `ai/contexts/frontend/SWIFTUI_PRINCIPLES.md`
- Sosumi MCP: `sosumi.searchAppleDocumentation(query)`
- Apple SwiftUI docs: Use Sosumi to search
- Task management: `ai/TODO.md`

---

**Report Generated:** 2026-02-12  
**Review Agent:** SwiftUI Architecture Specialist  
**Files Reviewed:** 113 Swift view files  
**Critical Issues:** 9  
**Total Issues:** 15
