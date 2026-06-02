import AppKit
import SwiftUI

// MARK: - Magnifier Panel (bottom bar - full width with zoom controls)

struct MagnifierPanelView: View {
    let image: NSImage
    let cursorPosition: CGPoint
    let imageSize: CGSize
    @Binding var magnification: CGFloat
    @Binding var panelHeight: CGFloat
    @Binding var isLocked: Bool
    var onLockToggle: () -> Void

    private let minMagnification: CGFloat = 0.25
    private let maxMagnification: CGFloat = 32.0
    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 400

    var body: some View {
        VStack(spacing: 0) {
            // Resize handle at top
            ResizeHandle(height: $panelHeight, minHeight: minHeight, maxHeight: maxHeight)

            ZStack(alignment: .bottomTrailing) {
                // Full width magnified view with scroll-to-zoom
                MagnifierPanelContent(
                    image: image,
                    cursorPosition: cursorPosition,
                    magnification: $magnification,
                    minMagnification: minMagnification,
                    maxMagnification: maxMagnification
                )

                // Lock indicator overlay (top-left when locked) - clickable to unlock
                if isLocked {
                    VStack {
                        HStack {
                            Button(action: onLockToggle) {
                                Image(systemName: "lock.fill")
                                    .font(.caption)
                                    .foregroundColor(.white)
                                    .padding(4)
                                    .background(Color.accentColor)
                                    .clipShape(RoundedRectangle(cornerRadius: 4))
                            }
                            .buttonStyle(.plain)
                            .help("Click to unlock magnifier")
                            .padding(8)
                            Spacer()
                        }
                        Spacer()
                    }
                }

                // Overlay controls and info
                HStack(spacing: 12) {
                    // Lock button
                    Button(action: onLockToggle) {
                        Image(systemName: isLocked ? "lock.fill" : "lock.open")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(isLocked ? .accentColor : .primary)
                    .help(isLocked ? "Unlock magnifier (follows cursor)" : "Lock magnifier (stays on current position)")

                    Divider()
                        .frame(height: 12)

                    // Height indicator
                    Text("\(Int(panelHeight))px")
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    Divider()
                        .frame(height: 12)

                    // Zoom controls
                    HStack(spacing: 4) {
                        Button(action: zoomOut) {
                            Image(systemName: "minus")
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .disabled(magnification <= minMagnification)

                        Text(String(format: "%.2gx", magnification))
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                            .frame(width: 44)

                        Button(action: zoomIn) {
                            Image(systemName: "plus")
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .disabled(magnification >= maxMagnification)
                    }

                    Divider()
                        .frame(height: 12)

                    // Coordinates
                    let pixelX = Int(cursorPosition.x * imageSize.width)
                    let pixelY = Int((1 - cursorPosition.y) * imageSize.height)

                    Text("X: \(pixelX)  Y: \(pixelY)")
                        .font(.caption)
                        .monospacedDigit()
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                // Thick (not ultraThin) material: this control bar overlaps the
                // magnified image, which is often bright (light document scans),
                // so a translucent backing left the labels invisible. Keep the
                // overlap, give it an opaque-enough backdrop for contrast (#1530).
                .background(.thickMaterial)
                .cornerRadius(4)
                .padding(8)
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .overlay(
            // Blue border when locked
            RoundedRectangle(cornerRadius: 0)
                .stroke(isLocked ? Color.accentColor : Color.clear, lineWidth: 2)
        )
    }

    private func zoomIn() {
        magnification = min(magnification * 1.5, maxMagnification)
    }

    private func zoomOut() {
        magnification = max(magnification / 1.5, minMagnification)
    }
}

// MARK: - Resize Handle for Panel

struct ResizeHandle: View {
    @Binding var height: CGFloat
    let minHeight: CGFloat
    let maxHeight: CGFloat

    @State private var isDragging = false

    var body: some View {
        Rectangle()
            .fill(Color.gray.opacity(0.3))
            .frame(height: 6)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.gray.opacity(isDragging ? 0.8 : 0.5))
                    .frame(width: 40, height: 4)
            )
            .contentShape(Rectangle())
            .gesture(
                DragGesture()
                    .onChanged { value in
                        isDragging = true
                        // Dragging up increases height (negative translation)
                        let newHeight = height - value.translation.height
                        height = max(minHeight, min(maxHeight, newHeight))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeUpDown.push()
                } else {
                    NSCursor.pop()
                }
            }
    }
}

// MARK: - Magnifier Panel Content (NSView wrapper)

struct MagnifierPanelContent: NSViewRepresentable {
    let image: NSImage
    let cursorPosition: CGPoint
    @Binding var magnification: CGFloat
    let minMagnification: CGFloat
    let maxMagnification: CGFloat

    func makeNSView(context: Context) -> NSView {
        let view = MagnifierPanelNSView()
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        view.minMagnification = minMagnification
        view.maxMagnification = maxMagnification
        view.onMagnificationChanged = { newMag in
            Task { @MainActor in
                self.magnification = newMag
            }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let panelView = nsView as? MagnifierPanelNSView else { return }
        panelView.image = image
        panelView.cursorPosition = cursorPosition
        panelView.magnification = magnification
        panelView.needsDisplay = true
    }
}

class MagnifierPanelNSView: NSView {
    var image: NSImage?
    var cursorPosition: CGPoint = .zero
    var magnification: CGFloat = 4.0
    var minMagnification: CGFloat = 0.25
    var maxMagnification: CGFloat = 16.0
    var onMagnificationChanged: ((CGFloat) -> Void)?

    override var acceptsFirstResponder: Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(
            rect: bounds,
            options: [.activeInKeyWindow, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        ))
    }

    override func scrollWheel(with event: NSEvent) {
        // Pinch-to-zoom when mouse is over magnifier panel
        let delta = event.scrollingDeltaY
        let newMag = magnification + delta * 0.1
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func magnify(with event: NSEvent) {
        // Handle pinch gesture
        let newMag = magnification * (1 + event.magnification)
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        guard let image = image, bounds.width > 0, bounds.height > 0 else { return }

        // The panel should show a strip of the image at the specified magnification
        // Calculate how much of the source image we need to fill the panel at this magnification
        let sourceWidth = bounds.width / magnification
        let sourceHeight = bounds.height / magnification

        // Center on cursor position.
        // TrackingImageView computes cursorPosition in AppKit bottom-up coords
        // (cursorPosition.y = 0 at bottom, = 1 at top), and NSImage.draw(in:from:)
        // also uses AppKit bottom-up coords — so the mapping is DIRECT, no flip.
        // (An earlier version flipped Y to fix an unrelated offset, but that was
        // actually caused by bounds-vs-image-dimensions; once the normalization
        // was fixed to subtract centering offset, the flip became wrong.)
        let centerX = cursorPosition.x * image.size.width
        let centerY = cursorPosition.y * image.size.height

        var sourceRect = NSRect(
            x: centerX - sourceWidth / 2,
            y: centerY - sourceHeight / 2,
            width: sourceWidth,
            height: sourceHeight
        )

        // Clamp to image bounds
        if sourceRect.minX < 0 { sourceRect.origin.x = 0 }
        if sourceRect.minY < 0 { sourceRect.origin.y = 0 }
        if sourceRect.maxX > image.size.width { sourceRect.origin.x = image.size.width - sourceWidth }
        if sourceRect.maxY > image.size.height { sourceRect.origin.y = image.size.height - sourceHeight }

        // Draw the source region scaled up to fill the entire view
        image.draw(in: bounds, from: sourceRect, operation: .copy, fraction: 1.0)
    }
}
