import SwiftUI
import AppKit
import OSLog

// MARK: - Zoomable Image Preview (with controls and magnifier)

struct ZoomableImagePreview: View {
    let url: URL

    private static let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ZoomableImagePreview")

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
    @State private var minScale: CGFloat = 0.1
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Current cursor position over image
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1
    @State private var imageCoordinator: ImageWithCursorTracking.Coordinator?

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

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active
                if let img = image, visibleRect.width < 0.99 || visibleRect.height < 0.99 || loupeEnabled {
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
            Self.logger.info("ZoomableImagePreview onAppear: loading \(url.lastPathComponent)")
            image = NSImage(contentsOf: url)
            if let img = image {
                imageSize = img.size
                Self.logger.info("Successfully loaded image: size=\(img.size.width)x\(img.size.height)")
            } else {
                Self.logger.error("Failed to load NSImage from: \(url.path)")
            }
        }
        .onChange(of: url) { _, newURL in
            Self.logger.info("ZoomableImagePreview URL changed: loading \(newURL.lastPathComponent)")
            image = NSImage(contentsOf: newURL)
            if let img = image {
                imageSize = img.size
                Self.logger.info("Successfully loaded new image: size=\(img.size.width)x\(img.size.height)")
            } else {
                Self.logger.error("Failed to load NSImage from: \(newURL.path)")
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
        .focusedSceneValue(\.imageZoomActions, ImageZoomActions(
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            actualSize: actualSize,
            zoomToFit: fitToWindow,
            canZoomIn: scale < maxScale,
            canZoomOut: scale > minScale,
            currentScale: scale
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
        // Calculate fit scale from coordinator if available
        if let fitScale = imageCoordinator?.calculateFitScale() {
            withAnimation(.easeInOut(duration: 0.2)) {
                scale = fitScale
            }
            // Center the content after a brief delay to let the scale apply
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(0.25))
                imageCoordinator?.centerContent()
            }
        }
    }

    private func actualSize() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = 1.0
        }
    }
}
