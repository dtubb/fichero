# AppKit Usage Audit Report

Generated: 2025-12-31

## Summary

- **AppKit imports**: 6 files
- **NSLog usage**: 88 instances across codebase
- **NSViewRepresentable**: 4 custom AppKit wrappers
- **Verdict**: Most AppKit usage is **necessary**, but NSLog should be replaced with OSLog

---

## 1. NSLog Usage (88 instances) - SHOULD REPLACE ✅

### Current State
NSLog is used extensively for debugging and logging across:
- Models/DocumentStore.swift (12 instances)
- Models/WorkflowStore.swift (1 instance)
- Views/Sidebar/SidebarView.swift (8 instances)
- Views/Chat/ChatInspector.swift (5 instances)
- Views/Library/FolderAccessManager.swift (5 instances)
- Services/* (57 instances across all service files)

### Recommendation
**Replace ALL NSLog with OSLog/Logger** for:
- Better performance (OSLog is optimized)
- Structured logging with categories
- Privacy-preserving logging
- Console.app integration
- Levels (debug, info, error)

### Pattern to Replace
```swift
// OLD:
NSLog("[DocumentStore] Loading documents...")

// NEW:
logger.info("[DocumentStore] Loading documents...")
```

Many files already have Logger instances defined but still use NSLog.

---

## 2. File Dialogs - MUST KEEP ❌

### Files Using
- **FicheroApp.swift**: NSSavePanel (line 298)
- **Views/Library/FolderAccessManager.swift**: NSOpenPanel (lines 37-50)
- **Views/Sidebar/SidebarView.swift**: NSOpenPanel (line 364)

### Reason
SwiftUI's `fileImporter()` and `fileExporter()` modifiers don't support:
- Security-scoped bookmarks (required for sandbox)
- Custom panel configuration
- Folder-only selection with custom prompts

These **MUST** remain AppKit.

---

## 3. NSViewRepresentable Wrappers - MOSTLY NECESSARY ⚠️

### 3.1 ImageViewerComponents.swift - NECESSARY ❌

**Usage**: Custom image viewer with zoom, pan, magnifier
- `ImageWithCursorTracking`: NSScrollView wrapper for high-performance image viewing
- `TrackingImageView`: NSImageView subclass for cursor tracking
- `MagnifierOverlay`: Custom NSView for magnification loupe

**Reason**: SwiftUI Image doesn't support:
- Smooth scrolling/zooming of large images
- Cursor position tracking for magnifier
- Custom drawing for loupe overlay
- NSImage direct manipulation

**Verdict**: Keep as-is. Core image viewing functionality.

### 3.2 ScrollWheelZoom.swift - POTENTIALLY REMOVABLE ✅

**Usage**: `ScrollWheelZoomView` NSViewRepresentable for scroll wheel zoom

**Reason**: Uses NSScrollView for custom scroll wheel handling

**Investigation Needed**: Check if SwiftUI's `.gesture()` with `MagnificationGesture` can replace this. Trackpad pinch-to-zoom works in SwiftUI, but scroll wheel zoom might need AppKit.

### 3.3 QuickLookComponents.swift - NECESSARY ❌

**Usage**: `QuickLookPreviewView` NSViewRepresentable for QuickLook

**Reason**: Uses `QLPreviewView` (QuickLook framework) which has no SwiftUI equivalent

**Verdict**: Keep as-is. System QuickLook integration.

### 3.4 MagnifierPanel.swift - REVIEW ⚠️

**Usage**: `MagnifierPanelContent` NSViewRepresentable for magnifier panel

**Reason**: Custom NSView for floating magnifier window

**Investigation Needed**: Could potentially be rewritten in SwiftUI with `.overlay()` and GeometryReader, but current implementation is working.

---

## 4. NS* Classes - NECESSARY ❌

### NSPasteboard (DocumentInspector.swift)
```swift
NSPasteboard.general.clearContents()
NSPasteboard.general.setString(text, forType: .string)
```
**Reason**: SwiftUI doesn't have pasteboard API. Required for copy functionality.

### NSWorkspace (EditorView.swift)
```swift
NSWorkspace.shared.activateFileViewerSelecting([url])  // Reveal in Finder
NSWorkspace.shared.open(url)                           // Open file
```
**Reason**: SwiftUI doesn't have Finder integration. Required for "Reveal in Finder" and "Open With" features.

### NSImage (ImageViewerComponents.swift, NavigatorMiniMap.swift)
**Reason**: Loading and manipulating images at low level. SwiftUI Image is higher-level.

---

## 5. AppKit Imports Summary

| File | Reason | Can Remove? |
|------|--------|-------------|
| FicheroApp.swift | NSSavePanel | ❌ No |
| FolderAccessManager.swift | NSOpenPanel, security bookmarks | ❌ No |
| ImageViewerComponents.swift | NSImageView, NSScrollView, custom drawing | ❌ No |
| ScrollWheelZoom.swift | NSScrollView for scroll wheel events | ✅ Maybe |
| QuickLookComponents.swift | QLPreviewView | ❌ No |
| MagnifierPanel.swift | Custom NSView | ⚠️ Review |

---

## Recommendations

### Priority 1: Replace NSLog with OSLog (88 instances) ✅
**Impact**: High - Better performance, structured logging, privacy
**Effort**: Medium - Pattern replacement across all files
**Files to update**: All files with NSLog

### Priority 2: Investigate ScrollWheelZoom.swift ✅
**Impact**: Low - Minor AppKit reduction
**Effort**: Low - Test if SwiftUI gestures work
**Action**: Try replacing with SwiftUI `.gesture(MagnificationGesture())`

### Priority 3: Consider MagnifierPanel.swift refactor ⚠️
**Impact**: Low - Minor AppKit reduction  
**Effort**: High - Complete rewrite
**Action**: Keep current implementation unless magnifier needs redesign

### Keep As-Is ❌
- File dialogs (NSSavePanel, NSOpenPanel)
- NSPasteboard (clipboard)
- NSWorkspace (Finder integration)
- QuickLook wrapper
- Image viewer components

---

## Next Steps

1. **Replace all NSLog with Logger** - Systematic replacement
2. **Test ScrollWheelZoom** - Can SwiftUI handle scroll wheel zoom?
3. **Document remaining AppKit** - Add comments explaining why AppKit is required

