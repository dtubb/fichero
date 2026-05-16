import AppKit
import OSLog
import SwiftUI

// MARK: - Zoomable Image Preview (with controls and magnifier)

// swiftlint:disable:next type_body_length
struct ZoomableImagePreview: View {
    let url: URL
    var documentId: String?

    private static let logger = Logger(subsystem: "com.fichero.fichero", category: "ZoomableImagePreview")

    private var scaleKey: String? {
        documentId.map { "imageZoom_\($0)" }
    }

    @SceneStorage("imagePreview.zoomScalesByDocument") private var zoomScalesByDocumentJSON: String = "{}"

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false
    @AppStorage("imagePreview.loupeLocked") private var loupeLocked = false

    @State private var scale: CGFloat = 1.0
    @State private var minScale: CGFloat = 0.01
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?

    private func loadSavedScale(for key: String) -> CGFloat? {
        guard let data = zoomScalesByDocumentJSON.data(using: .utf8),
              let values = try? JSONDecoder().decode([String: Double].self, from: data),
              let saved = values[key],
              saved > 0 else {
            return nil
        }
        return CGFloat(saved)
    }

    private func saveScale(_ newScale: CGFloat, for key: String) {
        var values: [String: Double] = [:]
        if let data = zoomScalesByDocumentJSON.data(using: .utf8),
           let decoded = try? JSONDecoder().decode([String: Double].self, from: data) {
            values = decoded
        }
        values[key] = Double(newScale)
        if let encoded = try? JSONEncoder().encode(values),
           let json = String(data: encoded, encoding: .utf8) {
            zoomScalesByDocumentJSON = json
        }
    }

    /// The position to use for magnifier (locked or cursor)
    private var magnifierPosition: CGPoint {
        magnifierLocked ? lockedPosition : cursorPosition
    }

    var body: some View {
        VStack(spacing: 0) {
            // Zoom toolbar
            HStack(spacing: 12) {
                Button(action: zoomOut) {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom Out")

                Text("\(Int(scale * 100))%")
                    .font(.caption)
                    .monospacedDigit()
                    .frame(width: 50)

                Button(action: zoomIn) {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom In")

                Divider()
                    .frame(height: 16)

                Button(action: fitToWindow) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(.plain)
                .help("Fit to Window")

                Button(action: actualSize) {
                    Image(systemName: "1.square")
                }
                .buttonStyle(.plain)
                .help("Actual Size (100%)")

                Divider()
                    .frame(height: 16)

                // Magnifier panel toggle
                Button {
                    magnifierEnabled.toggle()
                } label: {
                    Image(systemName: "rectangle.bottomhalf.inset.filled")
                }
                .buttonStyle(.plain)
                .foregroundColor(magnifierEnabled ? .accentColor : .primary)
                .help("Magnifier Panel")

                // Loupe toggle with zoom controls
                HStack(spacing: 4) {
                    Button {
                        loupeEnabled.toggle()
                    } label: {
                        Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeEnabled ? .accentColor : .primary)
                    .help("Loupe (crosshairs follow cursor, Option+move to reposition, lock to freeze)")

                    if loupeEnabled {
                        Button {
                            loupeLocked.toggle()
                        } label: {
                            Image(systemName: loupeLocked ? "lock.fill" : "lock.open")
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(loupeLocked ? .accentColor : .secondary)
                        .help(loupeLocked ? "Unlock loupe (crosshairs follow cursor)" : "Lock loupe (freeze view)")

                        Text(String(format: "%.1fx", CGFloat(loupeMagnification)))
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary)
                            .frame(width: 32)

                        Text("\(Int(loupeSize))px")
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(.windowBackgroundColor))

            Divider()

            // Main content area
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 0) {
                    // Image view with cursor tracking and integrated loupe
                    ImageWithCursorTracking(
                        url: url,
                        scale: $scale,
                        cursorPosition: $cursorPosition,
                        imageSize: $imageSize,
                        visibleRect: $visibleRect,
                        minScale: minScale,
                        maxScale: maxScale,
                        loupeEnabled: loupeEnabled,
                        loupeLocked: loupeLocked,
                        loupeMagnification: Binding(
                            get: { CGFloat(loupeMagnification) },
                            set: { loupeMagnification = Double($0) }
                        ),
                        loupeSize: Binding(
                            get: { CGFloat(loupeSize) },
                            set: { loupeSize = Double($0) }
                        ),
                        coordinator: $imageCoordinator
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                    .background(Color(nsColor: NSColor(white: 0.88, alpha: 1.0)))

                    // Bottom magnifier panel
                    if magnifierEnabled, let img = image {
                        Divider()
                        MagnifierPanelView(
                            image: img,
                            cursorPosition: magnifierPosition,
                            imageSize: imageSize,
                            magnification: Binding(
                                get: { CGFloat(panelMagnification) },
                                set: { panelMagnification = Double($0) }
                            ),
                            panelHeight: Binding(
                                get: { CGFloat(panelHeight) },
                                set: { panelHeight = Double($0) }
                            ),
                            isLocked: $magnifierLocked,
                            onLockToggle: {
                                if !magnifierLocked {
                                    // Locking - save the current magnifier position
                                    lockedPosition = cursorPosition
                                }
                                magnifierLocked.toggle()
                            }
                        )
                        .frame(height: CGFloat(panelHeight))
                    }
                }

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active.
                // visibleRect starts at (0,0,0,0) before layout completes, which would
                // pass the "< 0.99" zoom check and flash the minimap on every image
                // load (#771). Require positive area so the predicate only fires once
                // the viewport has actually measured the image.
                let visibleRectIsMeasured = visibleRect.width > 0 && visibleRect.height > 0
                let isActuallyZoomed = visibleRectIsMeasured
                    && (visibleRect.width < 0.99 || visibleRect.height < 0.99)
                if let img = image, isActuallyZoomed || loupeEnabled {
                    NavigatorMiniMap(
                        image: img,
                        visibleRect: visibleRect,
                        onRectangleDragged: { normalizedOrigin in
                            imageCoordinator?.scrollToNormalizedPosition(normalizedOrigin)
                        }
                    )
                    .frame(width: 150, height: 100)
                    .padding(8)
                }
            }
        }
        .onAppear {
            image = NSImage(contentsOf: url)
            if let img = image {
                imageSize = img.size
            } else {
                Self.logger.error("Failed to load NSImage from: \(url.path)")
            }
            if let key = scaleKey {
                if let saved = loadSavedScale(for: key) {
                    scale = saved
                }
            }
        }
        .onChange(of: url) { _, newURL in
            image = NSImage(contentsOf: newURL)
            if let img = image {
                imageSize = img.size
            } else {
                Self.logger.error("Failed to load NSImage from: \(newURL.path)")
            }
            // Restore saved zoom for this scaleKey if present. Otherwise
            // leave scale untouched — the NSViewRepresentable's
            // updateNSView handles fit-to-window in the same frame as the
            // new image is set, so we don't go through a 1.0 intermediate
            // that would flash at 100%. (#773)
            if let key = scaleKey, let saved = loadSavedScale(for: key) {
                scale = saved
            }
        }
        .onChange(of: scale) { _, newScale in
            if let key = scaleKey {
                saveScale(newScale, for: key)
            }
        }
        .onKeyPress(.init("+"), phases: .down) { _ in
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("="), phases: .down) { _ in
            // Also handle = key (same as + without shift)
            zoomIn()
            return .handled
        }
        .onKeyPress(.init("-"), phases: .down) { _ in
            zoomOut()
            return .handled
        }
        .onKeyPress(.init("0"), phases: .down) { _ in
            actualSize()
            return .handled
        }
        .onChange(of: magnifierLocked) { wasLocked, isLocked in
            if isLocked && !wasLocked {
                // Locking via menu command - save current position
                lockedPosition = cursorPosition
            }
        }
        .onKeyPress(.init("9"), phases: .down) { _ in
            fitToWindow()
            return .handled
        }
        .onKeyPress(.leftArrow, phases: .down) { _ in
            panLeft()
            return .handled
        }
        .onKeyPress(.rightArrow, phases: .down) { _ in
            panRight()
            return .handled
        }
        .onKeyPress(.upArrow, phases: .down) { _ in
            panUp()
            return .handled
        }
        .onKeyPress(.downArrow, phases: .down) { _ in
            panDown()
            return .handled
        }
        .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            actualSize: actualSize,
            zoomToFit: fitToWindow,
            canZoomIn: scale < maxScale,
            canZoomOut: scale > minScale
        ))
    }

    // MARK: - Zoom Actions

    private func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    private func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    private func fitToWindow() {
        if let fitScale = imageCoordinator?.calculateFitScale() {
            scale = fitScale
            // Defer center to next run loop so magnification has applied
            DispatchQueue.main.async {
                imageCoordinator?.centerContent()
            }
        }
    }

    private func actualSize() {
        // #599: pixel 1:1 — one image pixel per display point. Setting
        // `scale = 1.0` (NSScrollView.magnification = 1.0) shows the image
        // at NSImage.size, which on TIFF files with DPI metadata is
        // *smaller* than the actual pixel dimensions — a 300 DPI TIFF at
        // 1200×900 pixels reports `size == 288×216 points`, so
        // magnification=1.0 shrinks the image to DPI-logical size, not
        // actual pixels. The ratio of pixelsWide to size.width gives the
        // magnification that maps one image pixel to one display point,
        // matching Preview.app's Actual Size / ⌘⌥0 behaviour on macOS.
        // Falls back to 1.0 if the image has no representations (vector
        // or corrupt TIFF) or if pixel ratio exceeds the current clamp
        // — maxScale=10 is a reasonable ceiling for a UI affordance.
        let pixelRatio: CGFloat
        if let image,
           let rep = image.representations.first,
           image.size.width > 0 {
            pixelRatio = CGFloat(rep.pixelsWide) / image.size.width
        } else {
            pixelRatio = 1.0
        }
        scale = min(max(pixelRatio, minScale), maxScale)
        DispatchQueue.main.async {
            imageCoordinator?.centerContent()
        }
    }

    private func panLeft() {
        panBy(deltaX: -80, deltaY: 0)
    }

    private func panRight() {
        panBy(deltaX: 80, deltaY: 0)
    }

    private func panUp() {
        panBy(deltaX: 0, deltaY: 80)
    }

    private func panDown() {
        panBy(deltaX: 0, deltaY: -80)
    }

    private func panBy(deltaX: CGFloat, deltaY: CGFloat) {
        imageCoordinator?.panBy(
            x: deltaX / max(scale, 0.01),
            y: deltaY / max(scale, 0.01)
        )
    }
}
