#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

/// Which way the magnifier strip lies (#5411, `magnifier.strip-follows-line-direction`): along the page's
/// lines, so it shows a stretch of ONE line -- under the page for horizontal lines, beside it for vertical.
enum MagnifierStrip {
    /// Vertical when most of the page's resolved line directions are vertical (`ttb`, `btt`); otherwise,
    /// on a tie, or with nothing resolved, horizontal. The page's majority, not the line under the
    /// pointer, so the strip does not jump sides as the pointer crosses a heading.
    static func axis(forLineDirections directions: [String]) -> Axis {
        let vertical = directions.filter { $0 == "ttb" || $0 == "btt" }.count
        return vertical * 2 > directions.count ? .vertical : .horizontal
    }

    /// Where the person put the strip (ruled 2026-10-04, `magnifier.strip-placement-is-the-persons`):
    /// an explicit choice wins over the lines; Automatic is the line-direction default.
    enum Placement: String, CaseIterable, Identifiable {
        case automatic = ""
        case bottom
        case side

        var id: String { rawValue }

        /// What a pane stored. Nothing stored is Automatic. The strings are only ever written by this
        /// menu, so an unknown one can only be a newer build's choice, and is read as Automatic too.
        init(stored: String) { self = Placement(rawValue: stored) ?? .automatic }

        var title: String {
            switch self {
            case .automatic: "Automatic"
            case .bottom: "Bottom"
            case .side: "Side"
            }
        }
    }

    /// The pane option the choice is kept under (`@PaneStorage`: per pane, survives relaunch).
    static let placementKey = "imagePreview.magnifierStripPlacement"

    static func axis(placement: Placement, lineDirections: [String]) -> Axis {
        switch placement {
        case .automatic: axis(forLineDirections: lineDirections)
        case .bottom: .horizontal
        case .side: .vertical
        }
    }
}

#if canImport(AppKit)

// MARK: - Magnifier Panel (a strip along the page's lines, with zoom controls)

struct MagnifierPanelView: View {
    let image: PlatformImage
    let cursorPosition: CGPoint
    let imageSize: CGSize
    @Binding var magnification: CGFloat
    /// The strip's thickness: its height under the page, its width beside it.
    @Binding var panelHeight: CGFloat
    @Binding var isLocked: Bool
    var onLockToggle: () -> Void
    /// Where the person put the strip, this pane's choice (`magnifier.strip-placement-is-the-persons`).
    @Binding var placement: MagnifierStrip.Placement
    /// `.vertical`: a strip at the page's trailing side, for vertical lines (#5411).
    var axis: Axis = .horizontal

    private let minMagnification: CGFloat = 0.25
    private let maxMagnification: CGFloat = 32.0
    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 400

    /// The handle leads the strip (its top under the page, its leading edge beside it), so it always faces
    /// the page it resizes against.
    private var stripLayout: AnyLayout {
        axis == .vertical ? AnyLayout(HStackLayout(spacing: 0)) : AnyLayout(VStackLayout(spacing: 0))
    }

    /// The lock, thickness and zoom controls run along the strip: a column in a strip beside the page,
    /// which is too narrow for them in a row.
    private var controlsLayout: AnyLayout {
        axis == .vertical ? AnyLayout(VStackLayout(spacing: 8)) : AnyLayout(HStackLayout(spacing: 12))
    }

    /// Where the strip goes, the person's choice (ruled 2026-10-04): Automatic follows the page's lines.
    private var placementMenu: some View {
        Menu {
            Picker("Strip Position", selection: $placement) {
                ForEach(MagnifierStrip.Placement.allCases) { option in
                    Text(option.title).tag(option)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: axis == .vertical ? "rectangle.righthalf.inset.filled" : "rectangle.bottomhalf.inset.filled")
                .font(.caption)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .accessibilityLabel("Strip Position")
        .help("Where the magnifier strip goes: at the bottom, at the side, or Automatic (along the page's lines)")
    }

    var body: some View {
        stripLayout {
            // Resize handle on the side facing the page
            ResizeHandle(height: $panelHeight, minHeight: minHeight, maxHeight: maxHeight, axis: axis)
                .help(axis == .vertical
                      ? "Drag left or right to resize the magnifier strip (\(Int(minHeight))–\(Int(maxHeight))px)"
                      : "Drag up or down to resize the magnifier strip (\(Int(minHeight))–\(Int(maxHeight))px)")

            ZStack(alignment: .bottomTrailing) {
                // Full width magnified view with scroll-to-zoom
                MagnifierPanelContent(
                    image: image,
                    cursorPosition: cursorPosition,
                    magnification: $magnification,
                    minMagnification: minMagnification,
                    maxMagnification: maxMagnification
                )
                .help(isLocked
                      ? "Magnified view of the locked spot. Scroll up/down or pinch here to zoom; click the lock to follow the cursor again"
                      : "Magnified view under the cursor. Scroll up/down or pinch here to zoom; "
                        + "use the − / + buttons to step; click the lock to hold a spot")

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
                            .accessibilityLabel("Unlock magnifier")
                            .help("Magnifier is locked on a spot. Click to unlock and follow the cursor again")
                            .padding(8)
                            Spacer()
                        }
                        Spacer()
                    }
                }

                // Overlay controls and info
                controlsLayout {
                    // Lock button
                    Button(action: onLockToggle) {
                        Image(systemName: isLocked ? "lock.fill" : "lock.open")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(isLocked ? .accentColor : .primary)
                    .accessibilityLabel(isLocked ? "Unlock magnifier" : "Lock magnifier")
                    .help(isLocked
                          ? "Unlock magnifier — click to follow the cursor again"
                          : "Lock magnifier — click to hold the current spot while you move the cursor elsewhere")

                    placementMenu

                    Divider()
                        .frame(width: axis == .vertical ? 12 : nil, height: axis == .vertical ? nil : 12)

                    // Height indicator
                    Text("\(Int(panelHeight))px")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .help("Strip height. Drag the handle at the top edge of the strip to resize")

                    Divider()
                        .frame(width: axis == .vertical ? 12 : nil, height: axis == .vertical ? nil : 12)

                    // Zoom controls
                    HStack(spacing: 4) {
                        Button(action: zoomOut) {
                            Image(systemName: "minus")
                                .font(.caption)
                                // ponytail: the "−" glyph is a ~1pt-tall line, so a plain
                                // button's hit target was nearly unclickable; give both
                                // steppers the same square hit box.
                                .frame(width: 16, height: 16)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Zoom out")
                        .help("Zoom out one step (÷1.5) — click; or scroll down / pinch in over the strip")
                        .disabled(magnification <= minMagnification)

                        Text(String(format: "%.2gx", magnification))
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                            .frame(width: 44)
                            .help("Current magnification (\(String(format: "%.2g", minMagnification))×–\(Int(maxMagnification))×). "
                                  + "Use − / +, or scroll / pinch over the strip")

                        Button(action: zoomIn) {
                            Image(systemName: "plus")
                                .font(.caption)
                                .frame(width: 16, height: 16)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Zoom in")
                        .help("Zoom in one step (×1.5) — click; or scroll up / pinch out over the strip")
                        .disabled(magnification >= maxMagnification)
                    }

                    // The X/Y pixel readout is gone (Daniel, 2026-09-01): the
                    // strip is for LOOKING at the page, and a coordinate pair
                    // nobody acts on is just noise beside the controls.
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.thickMaterial)
                .cornerRadius(4)
                .padding(8)
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .overlay(
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
    /// The strip's thickness: its height under the page, its width beside it.
    @Binding var height: CGFloat
    let minHeight: CGFloat
    let maxHeight: CGFloat
    /// `.vertical`: the strip stands beside the page, so the handle is a bar on its leading edge and a
    /// drag to the left thickens it.
    var axis: Axis = .horizontal

    @State private var isDragging = false

    var body: some View {
        let vertical = axis == .vertical
        Rectangle()
            .fill(Color.gray.opacity(0.3))
            .frame(width: vertical ? 6 : nil, height: vertical ? nil : 6)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.gray.opacity(isDragging ? 0.8 : 0.5))
                    .frame(width: vertical ? 4 : 40, height: vertical ? 40 : 4)
            )
            .contentShape(Rectangle())
            .gesture(
                DragGesture()
                    .onChanged { value in
                        isDragging = true
                        let delta = vertical ? value.translation.width : value.translation.height
                        height = max(minHeight, min(maxHeight, height - delta))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
            .onHover { hovering in
                if hovering {
                    (vertical ? NSCursor.resizeLeftRight : NSCursor.resizeUpDown).push()
                } else {
                    NSCursor.pop()
                }
            }
    }
}

// MARK: - Magnifier Panel Content (NSView wrapper)

struct MagnifierPanelContent: NSViewRepresentable {
    let image: PlatformImage
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
    var image: PlatformImage?
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
        let delta = event.scrollingDeltaY
        let newMag = magnification + delta * 0.1
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func magnify(with event: NSEvent) {
        let newMag = magnification * (1 + event.magnification)
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        guard let image = image, bounds.width > 0, bounds.height > 0 else { return }

        let sourceWidth = bounds.width / magnification
        let sourceHeight = bounds.height / magnification

        let centerX = cursorPosition.x * image.size.width
        let centerY = cursorPosition.y * image.size.height

        var sourceRect = NSRect(
            x: centerX - sourceWidth / 2,
            y: centerY - sourceHeight / 2,
            width: sourceWidth,
            height: sourceHeight
        )

        if sourceRect.minX < 0 { sourceRect.origin.x = 0 }
        if sourceRect.minY < 0 { sourceRect.origin.y = 0 }
        if sourceRect.maxX > image.size.width { sourceRect.origin.x = image.size.width - sourceWidth }
        if sourceRect.maxY > image.size.height { sourceRect.origin.y = image.size.height - sourceHeight }

        image.draw(in: bounds, from: sourceRect, operation: .copy, fraction: 1.0)
    }
}

#elseif canImport(UIKit)

// MARK: - iOS Magnifier Panel

struct MagnifierPanelView: View {
    let image: PlatformImage
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
            ResizeHandle(height: $panelHeight, minHeight: minHeight, maxHeight: maxHeight)

            ZStack(alignment: .bottomTrailing) {
                MagnifierPanelContent(
                    image: image,
                    cursorPosition: cursorPosition,
                    magnification: $magnification,
                    minMagnification: minMagnification,
                    maxMagnification: maxMagnification
                )

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
                            .accessibilityLabel("Unlock magnifier")
                            .padding(8)
                            Spacer()
                        }
                        Spacer()
                    }
                }

                HStack(spacing: 12) {
                    Button(action: onLockToggle) {
                        Image(systemName: isLocked ? "lock.fill" : "lock.open")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(isLocked ? .accentColor : .primary)
                    .accessibilityLabel(isLocked ? "Unlock magnifier" : "Lock magnifier")
                    .help(isLocked ? "Unlock magnifier (follows cursor)" : "Lock magnifier (stays on current position)")

                    Divider()
                        .frame(height: 12)

                    Text("\(Int(panelHeight))px")
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    Divider()
                        .frame(height: 12)

                    HStack(spacing: 4) {
                        Button(action: zoomOut) {
                            Image(systemName: "minus")
                                .font(.caption)
                                .frame(width: 24, height: 24) // same hit-box fix as Mac; touch-sized
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Zoom out")
                        .help("Zoom out one step (÷1.5) — tap; or pinch in over the strip")
                        .disabled(magnification <= minMagnification)

                        Text(String(format: "%.2gx", magnification))
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                            .frame(width: 44)

                        Button(action: zoomIn) {
                            Image(systemName: "plus")
                                .font(.caption)
                                .frame(width: 24, height: 24)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Zoom in")
                        .help("Zoom in one step (×1.5) — tap; or pinch out over the strip")
                        .disabled(magnification >= maxMagnification)
                    }

                    // No X/Y readout — see the macOS strip (Daniel, 2026-09-01).
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.thickMaterial)
                .cornerRadius(4)
                .padding(8)
            }
        }
        .background(Color(uiColor: .systemBackground))
        .overlay(
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

// MARK: - iOS Resize Handle

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
                        let newHeight = height - value.translation.height
                        height = max(minHeight, min(maxHeight, newHeight))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
    }
}

// MARK: - iOS Magnifier Panel Content

struct MagnifierPanelContent: View {
    let image: PlatformImage
    let cursorPosition: CGPoint
    @Binding var magnification: CGFloat
    let minMagnification: CGFloat
    let maxMagnification: CGFloat

    @State private var pinchStartMagnification: CGFloat?

    var body: some View {
        GeometryReader { geometry in
            let panelSize = geometry.size
            let centerX = cursorPosition.x * image.size.width
            let centerY = (1.0 - cursorPosition.y) * image.size.height
            let offsetX = panelSize.width / 2 - magnification * centerX
            let offsetY = panelSize.height / 2 - magnification * centerY

            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: .fill)
                .frame(
                    width: image.size.width * magnification,
                    height: image.size.height * magnification
                )
                .offset(x: offsetX, y: offsetY)
                .frame(width: panelSize.width, height: panelSize.height)
                .clipped()
                .contentShape(Rectangle())
                .gesture(
                    MagnificationGesture()
                        .onChanged { value in
                            if pinchStartMagnification == nil {
                                pinchStartMagnification = magnification
                            }
                            let newMag = pinchStartMagnification! * value
                            magnification = max(minMagnification, min(maxMagnification, newMag))
                        }
                        .onEnded { _ in
                            pinchStartMagnification = nil
                        }
                )
        }
    }
}

#endif
