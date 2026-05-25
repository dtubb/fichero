# #928 Loupe for PDFs + Image Zoom Persistence Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add magnifier/loupe support to PDF viewing (currently image-only), and fix image loupe sizing + z-order issues during zoom operations.

**Architecture:** 
- Add loupe controls to `PDFPageView` toolbar mirroring `ZoomableImagePreview` (enable/lock toggles, magnification slider, size controls)
- Implement cursor tracking on PDFView via NSView subclass + gesture recognizer (similar to ImageWithCursorTracking pattern)
- Draw loupe circle overlay showing magnified region from PDF at cursor position
- Fix image loupe: ensure loupe coordinates map correctly to zoomed image content, lock loupe visibility during scale changes

**Tech Stack:** SwiftUI, AppKit (PDFKit, NSView), Core Graphics for overlay rendering

---

## File Structure

| File | Purpose |
|---|---|
| `PDFPageView.swift` | Add loupe toggle, controls, cursor tracking coordinator |
| `ImageViewerComponents.swift` | Fix coordinate tracking + z-order for image loupe during zoom |
| **New:** `PDFLoupeOverlay.swift` | Reusable PDF loupe rendering component |

---

## Task 1: Add Loupe Controls to PDFPageView Toolbar

**Files:**
- Modify: `fichero/fichero/Views/Library/PDFPageView.swift` (toolbar section + state)

- [ ] **Step 1: Add AppStorage properties for PDF loupe settings**

In `PDFPageView`, after the existing `zoomController` property, add:

```swift
struct PDFPageView: NSViewRepresentable {
    let path: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    var zoomController: PDFZoomController?

    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false
```

- [ ] **Step 2: Add @State for cursor position (needed by coordinator)**

```swift
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
```

- [ ] **Step 3: Update makeCoordinator to pass loupe bindings**

Change:
```swift
func makeCoordinator() -> Coordinator {
    Coordinator(owner: self)
}
```

To:
```swift
func makeCoordinator() -> Coordinator {
    Coordinator(
        owner: self,
        loupeEnabled: $loupeEnabled,
        cursorPosition: $cursorPosition,
        lockedPosition: $lockedPosition
    )
}
```

- [ ] **Step 4: Update Coordinator init to accept loupe bindings**

In the `Coordinator` class (inside PDFPageView), change:

```swift
@MainActor
final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
    var owner: PDFPageView
    weak var pdfView: PDFView?
    var zoomController: PDFZoomController?
    private var panAccumulated: CGFloat = 0

    init(owner: PDFPageView) {
        self.owner = owner
    }
```

To:

```swift
@MainActor
final class Coordinator: NSObject, PDFViewDelegate, NSGestureRecognizerDelegate {
    var owner: PDFPageView
    weak var pdfView: PDFView?
    var zoomController: PDFZoomController?
    private var panAccumulated: CGFloat = 0
    
    var loupeEnabled: Binding<Bool>
    var cursorPosition: Binding<CGPoint>
    var lockedPosition: Binding<CGPoint>

    init(
        owner: PDFPageView,
        loupeEnabled: Binding<Bool>,
        cursorPosition: Binding<CGPoint>,
        lockedPosition: Binding<CGPoint>
    ) {
        self.owner = owner
        self.loupeEnabled = loupeEnabled
        self.cursorPosition = cursorPosition
        self.lockedPosition = lockedPosition
    }
```

- [ ] **Step 5: Commit**

```bash
git add fichero/fichero/Views/Library/PDFPageView.swift
git commit -m "feat: add loupe state management to PDFPageView"
```

---

## Task 2: Implement Cursor Tracking for PDFView

**Files:**
- Modify: `fichero/fichero/Views/Library/PDFPageView.swift` (add NSTrackingArea in coordinator)

- [ ] **Step 1: Add updateTrackingAreas to Coordinator**

In the `Coordinator` class, add:

```swift
@objc
func updateTrackingAreas(_ notification: Notification) {
    guard let pdfView = pdfView else { return }
    
    // Remove old tracking areas
    pdfView.trackingAreas.forEach { pdfView.removeTrackingArea($0) }
    
    // Add new tracking area that covers the entire PDFView
    let tracking = NSTrackingArea(
        rect: pdfView.bounds,
        options: [.activeInKeyWindow, .mouseMoved, .inVisibleRect],
        owner: self,
        userInfo: nil
    )
    pdfView.addTrackingArea(tracking)
}
```

- [ ] **Step 2: Add mouseMoved handler to track cursor**

```swift
override func mouseMoved(with event: NSEvent) {
    guard loupeEnabled.wrappedValue else { return }
    guard let pdfView = pdfView, pdfView.bounds.width > 0, pdfView.bounds.height > 0 else { return }
    
    let locationInView = pdfView.convert(event.locationInWindow, from: nil)
    
    // Normalize to 0-1 range (PDFView coordinates: origin bottom-left)
    let normalized = CGPoint(
        x: locationInView.x / pdfView.bounds.width,
        y: locationInView.y / pdfView.bounds.height
    )
    
    cursorPosition.wrappedValue = normalized
}
```

- [ ] **Step 3: Register tracking area update in makeNSView**

In the `makeNSView` method of PDFPageView, after adding gesture recognizers, add:

```swift
    // Register for tracking area updates
    NotificationCenter.default.addObserver(
        context.coordinator,
        selector: #selector(Coordinator.updateTrackingAreas(_:)),
        name: NSView.frameDidChangeNotification,
        object: view
    )
    context.coordinator.updateTrackingAreas(NSNotification(name: NSView.frameDidChangeNotification, object: view))
```

- [ ] **Step 4: Clean up tracking areas in dismantleNSView**

Update the `dismantleNSView` method:

```swift
static func dismantleNSView(_ view: PDFView, coordinator: Coordinator) {
    NotificationCenter.default.removeObserver(coordinator)
    view.trackingAreas.forEach { view.removeTrackingArea($0) }
}
```

- [ ] **Step 5: Commit**

```bash
git add fichero/fichero/Views/Library/PDFPageView.swift
git commit -m "feat: add cursor tracking to PDFPageView for loupe support"
```

---

## Task 3: Create PDFLoupeOverlay Component

**Files:**
- Create: `fichero/fichero/Views/Library/PDFLoupeOverlay.swift`

- [ ] **Step 1: Write PDFLoupeOverlay NSViewRepresentable**

```swift
import PDFKit
import SwiftUI

/// Renders a magnified loupe circle overlay on top of a PDFView.
/// Shows a zoomed-in region of the PDF centered on the cursor position.
struct PDFLoupeOverlay: NSViewRepresentable {
    let pdfView: PDFView?
    let cursorPosition: CGPoint  // Normalized 0-1 range
    let magnification: CGFloat
    let loupeSize: CGFloat
    
    func makeNSView(context: Context) -> NSView {
        let overlay = PDFLoupeNSView()
        overlay.wantsLayer = true
        return overlay
    }
    
    func updateNSView(_ nsView: NSView, context: Context) {
        guard let overlay = nsView as? PDFLoupeNSView else { return }
        overlay.pdfView = pdfView
        overlay.cursorPosition = cursorPosition
        overlay.magnification = magnification
        overlay.loupeSize = loupeSize
        overlay.needsDisplay = true
    }
}

// MARK: - PDFLoupeNSView

class PDFLoupeNSView: NSView {
    var pdfView: PDFView?
    var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    var magnification: CGFloat = 3.0
    var loupeSize: CGFloat = 150.0
    
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        
        guard let pdfView = pdfView,
              let currentPage = pdfView.currentPage,
              let pdfImage = PDFPageImageRenderer.render(page: currentPage, scale: 2.0) else {
            return
        }
        
        // Calculate loupe circle position (center on cursor, accounting for bounds)
        let louperRadius = loupeSize / 2
        let loupeCenter = CGPoint(
            x: cursorPosition.x * bounds.width,
            y: (1 - cursorPosition.y) * bounds.height  // Flip Y for AppKit coords
        )
        
        // Calculate source region from the page (unmagnified)
        let sourceWidth = loupeSize / magnification
        let sourceHeight = loupeSize / magnification
        
        // Map cursor position (normalized to PDFView) to PDF page coordinates
        let pageWidth = pdfImage.size.width
        let pageHeight = pdfImage.size.height
        
        let centerX = cursorPosition.x * pageWidth
        let centerY = (1 - cursorPosition.y) * pageHeight
        
        var sourceRect = NSRect(
            x: centerX - sourceWidth / 2,
            y: centerY - sourceHeight / 2,
            width: sourceWidth,
            height: sourceHeight
        )
        
        // Clamp to page bounds
        sourceRect.origin.x = max(0, min(sourceRect.origin.x, pageWidth - sourceWidth))
        sourceRect.origin.y = max(0, min(sourceRect.origin.y, pageHeight - sourceHeight))
        
        // Draw magnified region into a circle
        let circlePath = NSBezierPath(ovalIn: NSRect(
            x: loupeCenter.x - louperRadius,
            y: loupeCenter.y - louperRadius,
            width: loupeSize,
            height: loupeSize
        ))
        
        // Save graphics state for clipping
        NSGraphicsContext.current?.saveGraphicsState()
        circlePath.addClip()
        
        // Draw the magnified portion
        let destRect = NSRect(
            x: loupeCenter.x - louperRadius,
            y: loupeCenter.y - louperRadius,
            width: loupeSize,
            height: loupeSize
        )
        pdfImage.draw(in: destRect, from: sourceRect, operation: .copy, fraction: 1.0)
        
        // Restore and draw circle outline
        NSGraphicsContext.current?.restoreGraphicsState()
        NSColor.accentColor.setStroke()
        circlePath.lineWidth = 2
        circlePath.stroke()
    }
}

// MARK: - PDFPageImageRenderer Helper

class PDFPageImageRenderer {
    static func render(page: PDFPage, scale: CGFloat) -> NSImage? {
        let pageRect = page.bounds(for: .mediaBox)
        let renderSize = NSRect(
            origin: .zero,
            size: CGSize(
                width: pageRect.width * scale,
                height: pageRect.height * scale
            )
        )
        
        guard let pdf = NSPDFImageRep(data: page.document?.dataRepresentation() ?? Data()) else {
            return nil
        }
        
        let image = NSImage(size: renderSize.size)
        image.lockFocus()
        defer { image.unlockFocus() }
        
        NSColor.white.setFill()
        renderSize.fill()
        
        page.draw(at: page.bounds(for: .mediaBox).origin)
        
        return image
    }
}
```

- [ ] **Step 2: Register file with Xcode project**

```bash
ruby scripts/add-swift-file.rb fichero/fichero/Views/Library/PDFLoupeOverlay.swift
```

- [ ] **Step 3: Commit**

```bash
git add fichero/fichero/Views/Library/PDFLoupeOverlay.swift fichero/fichero.xcodeproj
git commit -m "feat: create PDFLoupeOverlay component for magnified region rendering"
```

---

## Task 4: Wire Loupe Overlay into PDFPageView

**Files:**
- Modify: `fichero/fichero/Views/Library/PDFPageView.swift` (add overlay to view hierarchy)

- [ ] **Step 1: Create a wrapper view that includes the loupe overlay**

After the `PDFPageView` struct definition, add a new view that wraps it:

```swift
struct PDFPageWithLoupe: View {
    let path: String
    let pageIndex: Int
    var onPageIndexChange: ((Int) -> Void)?
    var zoomController: PDFZoomController?
    
    @AppStorage("pdfPreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("pdfPreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("pdfPreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("pdfPreview.loupeLocked") private var loupeLocked = false
    
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)
    @State private var pdfView: PDFView?
    
    var body: some View {
        ZStack {
            PDFPageView(
                path: path,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange,
                zoomController: zoomController
            )
            
            if loupeEnabled {
                PDFLoupeOverlay(
                    pdfView: pdfView,
                    cursorPosition: loupeLocked ? cursorPosition : cursorPosition,
                    magnification: loupeMagnification,
                    loupeSize: loupeSize
                )
                .allowsHitTesting(false)
            }
        }
    }
}
```

- [ ] **Step 2: Add loupe toolbar button to PDFPageWithLoupe**

Wrap the body with toolbar controls:

```swift
    var body: some View {
        ZStack {
            // ... loupe overlay code ...
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                if loupeEnabled {
                    Button(action: { loupeLocked.toggle() }) {
                        Image(systemName: loupeLocked ? "lock.fill" : "lock.open")
                    }
                    .foregroundColor(loupeLocked ? .accentColor : .primary)
                    .help(loupeLocked ? "Unlock loupe" : "Lock loupe")
                    
                    Text(String(format: "%.1fx", loupeMagnification))
                        .font(.caption)
                    
                    Slider(value: $loupeMagnification, in: 1...8, step: 0.5)
                        .frame(width: 80)
                }
                
                Button(action: { loupeEnabled.toggle() }) {
                    Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                }
                .foregroundColor(loupeEnabled ? .accentColor : .primary)
                .help("Toggle loupe")
            }
        }
    }
```

- [ ] **Step 3: Update any places that use PDFPageView to use PDFPageWithLoupe**

Search for usages:
```bash
grep -r "PDFPageView(" fichero/fichero/Views --include="*.swift" | grep -v "struct PDFPageView"
```

Replace each with `PDFPageWithLoupe`.

- [ ] **Step 4: Commit**

```bash
git add fichero/fichero/Views/Library/PDFPageView.swift
git commit -m "feat: wire PDFLoupeOverlay into PDFPageView with toolbar controls"
```

---

## Task 5: Fix Image Loupe Coordinate Tracking During Zoom

**Files:**
- Modify: `fichero/fichero/Views/Library/ImageViewerComponents.swift` (loupe coordinate transform)

- [ ] **Step 1: Fix cursor position tracking in ImageWithCursorTracking**

Find the `ImageWithCursorTracking` NSViewRepresentable. Update the `Coordinator` to properly transform cursor coordinates when the image is zoomed:

In the `mouseMoved` handler, change:

```swift
override func mouseMoved(with event: NSEvent) {
    guard let imageView = self.imageView else { return }
    
    let location = imageView.convert(event.locationInWindow, from: nil)
    let normalized = CGPoint(
        x: location.x / imageView.bounds.width,
        y: location.y / imageView.bounds.height
    )
    
    Task { @MainActor in
        owner.cursorPosition = normalized
    }
}
```

To account for scroll position and zoom:

```swift
override func mouseMoved(with event: NSEvent) {
    guard let imageView = self.imageView else { return }
    
    // Get the location in image view coordinates
    let locationInWindow = event.locationInWindow
    let locationInView = imageView.convert(locationInWindow, from: nil)
    
    // Account for scroll view offset if present
    var adjustedLocation = locationInView
    if let scrollView = imageView.enclosingScrollView {
        let clipBounds = scrollView.contentView.bounds
        adjustedLocation.x += clipBounds.minX
        adjustedLocation.y += clipBounds.minY
    }
    
    // Normalize to 0-1 range based on actual image size (not view size)
    let normalized = CGPoint(
        x: adjustedLocation.x / (owner.imageSize.width * owner.scale),
        y: adjustedLocation.y / (owner.imageSize.height * owner.scale)
    )
    
    // Clamp to 0-1 range
    let clamped = CGPoint(
        x: max(0, min(1, normalized.x)),
        y: max(0, min(1, normalized.y))
    )
    
    Task { @MainActor in
        owner.cursorPosition = clamped
    }
}
```

- [ ] **Step 2: Ensure loupe stays visible during zoom (z-order fix)**

In `ZoomableImagePreview` body, move the loupe overlay AFTER the image view in the ZStack so it renders on top:

Find:
```swift
ZStack(alignment: .topLeading) {
    // Image view
    imageView
    
    if loupeEnabled {
        loupeOverlay
    }
}
```

Ensure the ZStack has proper layer ordering — the loupe should be the last element:

```swift
ZStack {
    VStack(spacing: 0) {
        // Toolbar
        HStack { ... }
        
        // Image view
        imageView
    }
    
    // Loupe overlay on top (drawn last = on top)
    if loupeEnabled {
        loupeOverlay
    }
}
```

- [ ] **Step 3: Prevent loupe size from changing during zoom**

The loupe size should be fixed in screen space, not scale with the image. In `ZoomableImagePreview`, ensure `loupeSize` is NOT multiplied by `scale`:

Current (wrong):
```swift
.frame(width: loupeSize * scale, height: loupeSize * scale)
```

Should be (fixed):
```swift
.frame(width: loupeSize, height: loupeSize)
```

Search for loupe-related frame modifiers and verify they use `loupeSize` directly, not multiplied by scale.

- [ ] **Step 4: Commit**

```bash
git add fichero/fichero/Views/Library/ImageViewerComponents.swift
git commit -m "fix: image loupe coordinate tracking and z-order during zoom"
```

---

## Task 6: Build + Test + Lint

**Files:**
- Test: Xcode build + SwiftLint

- [ ] **Step 1: Run SwiftLint**

```bash
swiftlint lint fichero/fichero/Views/Library/PDFPageView.swift fichero/fichero/Views/Library/PDFLoupeOverlay.swift fichero/fichero/Views/Library/ImageViewerComponents.swift
```

Expected: No violations (or fix any that appear)

- [ ] **Step 2: Build the project**

Open Xcode and run `⌘B` (Build), or:

```bash
xcodebuild -scheme Fichero -configuration Debug build
```

Expected: Build succeeds

- [ ] **Step 3: Run a quick preview test**

Open `PDFPageView.swift` and render a preview showing a PDF with the loupe enabled. Verify:
- Loupe toggle button appears
- Magnification slider appears when loupe is on
- Lock button works

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "build: #928 loupe implementation passes lint and builds"
```

---

## Task 7: Manual Testing (you do this)

- [ ] Open a PDF in the library, toggle loupe ON
- [ ] Move cursor over PDF → verify loupe circle appears and follows cursor
- [ ] Click lock button → loupe should freeze at that position
- [ ] Change magnification slider → loupe zoom should increase
- [ ] Zoom in/out on the PDF itself → loupe should remain visible and track correctly
- [ ] Open an image in the library, enable loupe
- [ ] Zoom in/out on the image → loupe size should remain constant, position should track zoomed image
- [ ] Verify loupe doesn't disappear during aggressive zoom operations
