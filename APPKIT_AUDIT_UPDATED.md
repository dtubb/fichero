# AppKit Usage Audit - UPDATED with Sosumi Verification

Generated: 2025-12-31 (Updated after Sosumi documentation check)

## Executive Summary

**Can be replaced with SwiftUI**: File dialogs, QuickLook, URL opening  
**Must keep AppKit**: Reveal in Finder, Pasteboard, Image viewer components  
**Priority**: Replace NSLog → OSLog (88 instances)

---

## Priority 1: Replace NSLog → OSLog ✅ (88 instances)

**Verified**: Should definitely be replaced  
**Reason**: Better performance, structured logging, privacy-preserving  
**Action**: Systematic replacement across all files

---

## Priority 2: Replace File Dialogs with SwiftUI ✅

### Current (AppKit):
```swift
let panel = NSOpenPanel()
panel.canChooseDirectories = true
// ... configuration
```

### SwiftUI Equivalent:
```swift
.fileImporter(isPresented: $showImporter, allowedContentTypes: [.directory]) { result in
    switch result {
    case .success(let url):
        let gotAccess = url.startAccessingSecurityScopedResource()
        // ... use url
        url.stopAccessingSecurityScopedResource()
    }
}
```

**Verification**: ✅ Sosumi docs confirm SwiftUI fileImporter supports security-scoped bookmarks  
**Files to update**:
- FicheroApp.swift (NSSavePanel)
- FolderAccessManager.swift (NSOpenPanel)
- SidebarView.swift (NSOpenPanel)

---

## Priority 3: Replace QuickLook with SwiftUI ✅

### Current (AppKit):
```swift
struct QuickLookPreviewView: NSViewRepresentable {
    // NSViewRepresentable wrapper for QLPreviewView
}
```

### SwiftUI Equivalent:
```swift
.quickLookPreview($selectedURL, in: urls)
```

**Verification**: ✅ Sosumi docs show SwiftUI has native QuickLook support  
**Files to update**:
- QuickLookComponents.swift

---

## Priority 4: Replace URL Opening (Partial) ⚠️

### Can Replace:
```swift
// OLD:
NSWorkspace.shared.open(url)

// NEW:
@Environment(\.openURL) private var openURL
openURL(url)
```

### Must Keep:
```swift
// NO SwiftUI equivalent for "Reveal in Finder":
NSWorkspace.shared.activateFileViewerSelecting([url])
```

**Verification**: ✅ openURL exists in SwiftUI, ❌ Reveal in Finder requires AppKit  
**Files to update**:
- EditorView.swift (partial - keep Reveal in Finder)

---

## Keep As-Is (No SwiftUI Alternative)

### 1. NSPasteboard ❌
**Reason**: No SwiftUI clipboard API  
**Usage**: DocumentInspector.swift - copy to clipboard  
**Verdict**: Keep AppKit

### 2. Reveal in Finder ❌
**Reason**: NSWorkspace.activateFileViewerSelecting has no SwiftUI equivalent  
**Usage**: EditorView.swift - "Reveal in Finder" command  
**Verdict**: Keep AppKit

### 3. Image Viewer Components ❌
**Reason**: High-performance image viewing with custom drawing  
**Usage**: ImageViewerComponents.swift - zoom, pan, magnifier  
**Components**:
- NSScrollView for smooth scrolling
- NSImageView for cursor tracking
- Custom NSView for magnifier overlay
**Verdict**: Keep AppKit (core functionality)

### 4. ScrollWheelZoom ⚠️
**Reason**: Need scroll wheel (not trackpad) support  
**Usage**: ScrollWheelZoom.swift  
**Action**: Test if SwiftUI MagnificationGesture handles scroll wheel  
**Verdict**: Probably keep, needs testing

### 5. MagnifierPanel ⚠️
**Reason**: Floating magnifier window  
**Usage**: MagnifierPanel.swift  
**Action**: Could potentially rewrite in SwiftUI  
**Verdict**: Keep for now (working implementation)

---

## Implementation Plan

### Phase 1: NSLog → OSLog (High Priority) ✅
- Impact: High - Better performance, structured logging
- Effort: Medium - 88 instances across all layers
- Risk: Low - Drop-in replacement

### Phase 2: File Dialogs → SwiftUI (Medium Priority) ✅
- Impact: Medium - Removes 3 AppKit imports
- Effort: Medium - Requires refactoring dialog presentation
- Risk: Medium - Security-scoped bookmarks must work correctly

### Phase 3: QuickLook → SwiftUI (Low Priority) ✅
- Impact: Low - Removes 1 AppKit import
- Effort: Low - SwiftUI modifier replacement
- Risk: Low - Native SwiftUI API

### Phase 4: URL Opening → SwiftUI (Partial) ⚠️
- Impact: Low - Minor AppKit reduction
- Effort: Low - Environment value replacement
- Risk: Low - Keep Reveal in Finder as AppKit

### Keep Forever: ❌
- NSPasteboard (clipboard)
- NSWorkspace.activateFileViewerSelecting (Reveal in Finder)
- Image viewer components (performance-critical)

---

## Final AppKit Footprint (After Refactoring)

**Remaining AppKit imports**: 2-3 files
1. **EditorView.swift** - Reveal in Finder (NSWorkspace)
2. **DocumentInspector.swift** - Clipboard (NSPasteboard)
3. **ImageViewerComponents.swift** - High-performance viewer (NSImageView/NSScrollView)

**AppKit completely removed from**: 3 files
1. FicheroApp.swift - Replace NSSavePanel with fileExporter
2. FolderAccessManager.swift - Replace NSOpenPanel with fileImporter
3. QuickLookComponents.swift - Replace with SwiftUI quickLookPreview

---

## Next Steps

1. ✅ **Complete NSLog → OSLog replacement** (all 88 instances)
2. Test file dialogs with SwiftUI (verify security-scoped bookmarks work)
3. Test QuickLook SwiftUI modifier (verify functionality matches)
4. Replace URL opening where applicable (keep Reveal in Finder)
5. Document remaining AppKit with comments explaining necessity

