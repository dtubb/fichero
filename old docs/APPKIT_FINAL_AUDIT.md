# AppKit Final Audit Report

## Summary

**Total AppKit imports**: 6 files
**Can be removed**: 0 files
**Must keep**: 6 files (all necessary)

## Analysis by File

### 1. FicheroApp.swift ❌ Must Keep

**AppKit Usage**: `NSSavePanel` (line 298)

```swift
let savePanel = NSSavePanel()
savePanel.allowedContentTypes = [.package]
savePanel.canCreateDirectories = true
savePanel.nameFieldStringValue = library.displayName + ".fichero"
savePanel.message = "Choose a location to save your library"
```

**Why Necessary**:
- SwiftUI's `fileExporter()` requires documents to conform to `ReferenceFileDocument` or `FileDocument`
- This code saves a library package to an arbitrary location, not a document
- No direct SwiftUI equivalent for arbitrary file/folder saving with custom UI

**Recommendation**: Keep NSSavePanel

---

### 2. FolderAccessManager.swift ❌ Must Keep

**AppKit Usage**: `NSOpenPanel` (line 39)

```swift
let panel = NSOpenPanel()
panel.canChooseFiles = false
panel.canChooseDirectories = true
panel.allowsMultipleSelection = false
panel.message = "Grant access to '\(folder.lastPathComponent)' folder"
panel.prompt = "Grant Access"
```

**Why Necessary**:
- Used to request security-scoped bookmark access to folders
- SwiftUI `fileImporter()` can select folders, but doesn't provide:
  - Custom message and prompt text
  - Direct control over directory URL for navigation
  - Same level of integration with security-scoped bookmarks
- Critical for sandbox file access permissions

**Recommendation**: Keep NSOpenPanel

---

### 3. ImageViewerComponents.swift ❌ Must Keep

**AppKit Usage**:
- `NSImage` (lines 25, 178, 184, 272, 316)
- `NSScrollView` (line 231)
- `NSImageView` (lines 338, 408, 444)
- `NSViewRepresentable` (line 218)
- `NSView.boundsDidChangeNotification` (line 288)

**Why Necessary**:
- Custom zoom/pan image viewer with pixel-perfect control
- Cursor tracking for magnifier position
- Scroll wheel zoom handling
- SwiftUI Image doesn't provide:
  - Direct pixel-level zoom control
  - Cursor position tracking within image
  - Integration with NSScrollView for smooth panning
  - Fine-grained scroll event handling

**Recommendation**: Keep all AppKit usage - this is a complex custom image viewer

---

### 4. MagnifierPanel.swift ❌ Must Keep

**AppKit Usage**:
- `NSImage` (line 7, 176)
- `NSViewRepresentable` (line 175)
- `NSView` (line 182)
- Custom NSView subclass: `MagnifierPanelNSView`

**Why Necessary**:
- Magnifier panel with loupe and pixel-level magnification
- Requires custom drawing and image manipulation
- SwiftUI doesn't support:
  - Pixel-level image region extraction and magnification
  - Custom drawing of magnified pixels
  - The level of control needed for a magnifier tool

**Recommendation**: Keep all AppKit usage - magnifier requires low-level control

---

### 5. QuickLookComponents.swift ❌ Must Keep (with caveat)

**AppKit Usage**:
- `QLPreviewView` wrapped in `NSViewRepresentable` (line 244)

**Why Necessary**:
- Embedded QuickLook preview within the app UI
- SwiftUI's `.quickLookPreview()` modifier:
  - Only shows modal/sheet presentation
  - Cannot be embedded in layout like this code requires
  - Different use case (modal vs embedded)

**Caveat**: If modal preview is acceptable instead of embedded, could use SwiftUI

**Recommendation**: Keep NSViewRepresentable wrapper unless modal preview is acceptable

---

### 6. ScrollWheelZoom.swift ❌ Must Keep

**AppKit Usage**:
- `NSViewRepresentable` (line 6)
- `NSView` (lines 11, 23)
- `NSEvent` (line 26)

```swift
class ScrollWheelCaptureView: NSView {
    var onScroll: ((CGFloat) -> Void)?

    override func scrollWheel(with event: NSEvent) {
        if event.phase == .changed || event.momentumPhase == .changed {
            let delta = event.scrollingDeltaY
            onScroll?(delta)
        }
    }
}
```

**Why Necessary**:
- Captures scroll wheel events for zoom control
- SwiftUI doesn't provide:
  - Direct access to NSEvent scroll wheel events
  - Fine-grained control over scroll delta
  - Ability to distinguish scroll phases (changed, momentum)
- Required for smooth scroll-to-zoom functionality

**Recommendation**: Keep all AppKit usage - scroll wheel event handling not available in SwiftUI

---

## Alternatives Investigated

### SwiftUI fileExporter()
- **Purpose**: Save files to disk
- **Limitation**: Requires ReferenceFileDocument or FileDocument protocol
- **Use case**: Document-based apps, not arbitrary file saving
- **Conclusion**: Cannot replace NSSavePanel for library saving

### SwiftUI fileImporter()
- **Purpose**: Import files/folders
- **Limitation**: Less control over UI (message, prompt, navigation)
- **Security**: Does support security-scoped bookmarks
- **Conclusion**: Could potentially replace NSOpenPanel but with UX degradation

### SwiftUI quickLookPreview()
- **Purpose**: Preview files
- **Limitation**: Modal presentation only, not embeddable
- **Conclusion**: Cannot replace embedded QLPreviewView

### SwiftUI Image + gestures
- **Purpose**: Display and interact with images
- **Limitation**: No pixel-level zoom control, cursor tracking, or scroll event access
- **Conclusion**: Cannot replace custom NSScrollView-based viewer

---

## Recommendations

### Immediate Actions
**None** - All AppKit usage is justified and necessary for current functionality

### Optional Future Improvements

1. **FolderAccessManager.swift**: Could migrate to SwiftUI `fileImporter()` if willing to accept:
   - Less customizable UI (no custom message/prompt)
   - Different UX flow
   - Need to verify security-scoped bookmark persistence works identically

2. **QuickLookComponents.swift**: Could use SwiftUI `.quickLookPreview()` if:
   - Modal presentation is acceptable instead of embedded
   - User is willing to change UX from embedded preview to sheet

### Not Recommended
- Do NOT replace ImageViewerComponents or MagnifierPanel AppKit usage
  - These require low-level control SwiftUI doesn't provide
  - Significant functionality loss
  - Would require complete rewrite with reduced capabilities

---

## Conclusion

All 6 files with AppKit imports have **legitimate, necessary** usage that cannot be easily replaced with SwiftUI without significant functionality loss or UX degradation.

**Final Status**: ✅ AppKit usage is minimal and justified
**Action Required**: None - keep current implementation
