import SwiftUI

// MARK: - Resize (#1748)

extension Spatial2DCanvas {
    /// The card's persisted size — the `CanvasItemLayout` w/h if present, else the
    /// default sticky-note size. View-space (pre-camera-scale) units.
    func persistedItemSize(for item: CanvasItemDisplay) -> CGSize {
        let row = layoutStore?.layout(for: scopeKey).first { $0.itemId == item.id }
        // Flatten the double-optional (row? + w?) before mapping, else the
        // type-checker chokes ("failed to produce diagnostic") inside CGSize.
        let savedW: Double? = row?.w ?? nil
        let savedH: Double? = row?.h ?? nil
        let width = savedW.map { CGFloat($0) } ?? CanvasItemView.defaultWidth
        let height = savedH.map { CGFloat($0) } ?? CanvasItemView.defaultHeight
        return CGSize(width: width, height: height)
    }

    /// Size used to render the card: the live drag size while resizing, else the
    /// persisted size.
    func itemSize(for item: CanvasItemDisplay) -> CGSize {
        resizeItemId == item.id ? resizeSize : persistedItemSize(for: item)
    }

    /// Native corner grab handle shown on a selected item; drag to resize.
    func resizeHandle(for item: CanvasItemDisplay) -> some View {
        // Keep the 12pt visual dot but expand the drag target to 44pt on touch
        // so a finger can grab it (#2806). Mac keeps the precise 12pt target.
        #if os(macOS)
        let hitTarget: CGFloat = 12
        #else
        let hitTarget: CGFloat = 44
        #endif
        return Circle()
            .fill(Color.accentColor)
            .overlay(Circle().stroke(.white, lineWidth: 1.5))
            .frame(width: 12, height: 12)
            .frame(width: hitTarget, height: hitTarget)
            .contentShape(Circle())
            .offset(x: 6, y: 6)
            .gesture(resizeGesture(for: item))
            .help("Drag to resize")
    }

    func resizeGesture(for item: CanvasItemDisplay) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                if resizeOrigin == nil {
                    resizeOrigin = persistedItemSize(for: item)
                    resizeItemId = item.id
                    // Same rule as beginning a drag (#4436): grabbing a resize
                    // handle on an item that is ALREADY selected keeps the
                    // selection. This was a bare replace, so resizing one card
                    // of a marqueed group silently threw the group away.
                    if !selectedNodeIds.contains(item.id) {
                        CanvasTapSelection.tap(
                            item.id,
                            selection: &selectedNodeIds,
                            anchor: &canvasSelectionAnchor,
                            modifiers: []
                        )
                    }
                }
                guard let origin = resizeOrigin else { return }
                let scale = effectiveZoom
                resizeSize = CGSize(
                    width: min(max(origin.width + value.translation.width / scale, 100), 480),
                    height: min(max(origin.height + value.translation.height / scale, 64), 480)
                )
            }
            .onEnded { _ in
                let final = resizeSize
                resizeOrigin = nil
                resizeItemId = nil
                resizeSize = .zero
                if final != .zero { persistItemSize(itemId: item.id, size: final) }
            }
    }
}

// MARK: - Add item menu

extension Spatial2DCanvas {
    /// Native "+" menu to add a standalone item to the canvas. Shown only when
    /// the canvas is interactive (a real item store + folder scope). The new
    /// item appears at its arranged fallback position until dragged.
    @ViewBuilder
    var addItemMenu: some View {
        if let store = itemStore, let folderId = folderScopeId {
            Menu {
                Button("Add Note") {
                    Task { await store.createItem(folderId: folderId, kind: .note, text: "New note") }
                }
                Button("Add Quote") {
                    Task { await store.createItem(folderId: folderId, kind: .quote, text: "New quote") }
                }
                Button("Add Text") {
                    Task { await store.createItem(folderId: folderId, kind: .text, text: "New text") }
                }
            } label: {
                Image(systemName: "plus")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .padding(8)
            .help("Add a note, quote, or text card to the canvas")
        }
    }
}

// MARK: - Camera & marquee gestures

extension Spatial2DCanvas {
    /// Background drag: pans the camera in `.pan` mode, draws a selection
    /// marquee in `.marquee` mode. A drag that starts on a node is intercepted
    /// by that chip's own gesture (child wins), so this only fires on empty
    /// canvas — that's how pan/node-drag/marquee are disambiguated.
    func backgroundGesture(layout: [String: CGPoint], in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .updating($livePan) { value, state, _ in
                if canvasMode == .pan { state = value.translation }
            }
            .onChanged { value in
                if canvasMode == .marquee {
                    marqueeRect = rect(from: value.startLocation, to: value.location)
                }
            }
            .onEnded { value in
                switch canvasMode {
                case .pan:
                    panOffset = CGSize(
                        width: panOffset.width + value.translation.width,
                        height: panOffset.height + value.translation.height
                    )
                case .marquee:
                    // Through the shared grammar (#4436): this replaced the
                    // selection wholesale, so a ⇧-marquee discarded what it was
                    // meant to extend. It also wrote a SECOND `marqueeSelection`
                    // set that the chips OR-ed into their own `isSelected` — a
                    // separate opinion about what "selected" draws as, which is
                    // how the canvas ended up looking selected while the rest of
                    // the app thought nothing was.
                    let box = rect(from: value.startLocation, to: value.location)
                    CanvasTapSelection.marquee(
                        nodesIntersecting(box, layout: layout, in: size),
                        selection: &selectedNodeIds,
                        anchor: &canvasSelectionAnchor
                    )
                    marqueeRect = nil
                }
            }
    }

    /// Trackpad pinch-to-zoom, clamped to `minZoom...maxZoom` on commit.
    var magnifyGesture: some Gesture {
        MagnifyGesture()
            .updating($pinchScale) { value, state, _ in state = value.magnification }
            .onEnded { value in
                zoom = min(max(zoom * value.magnification, minZoom), maxZoom)
            }
    }

    /// Build an axis-aligned rect from two drag corners.
    func rect(from start: CGPoint, to end: CGPoint) -> CGRect {
        CGRect(x: min(start.x, end.x), y: min(start.y, end.y),
               width: abs(start.x - end.x), height: abs(start.y - end.y))
    }

    /// Nodes whose transformed centre falls inside the marquee. Centre points
    /// are mapped through the same camera transform SwiftUI applies (scale
    /// about the canvas centre, then pan).
    func nodesIntersecting(_ box: CGRect, layout: [String: CGPoint], in size: CGSize) -> Set<String> {
        let centre = CGPoint(x: size.width / 2, y: size.height / 2)
        let scale = effectiveZoom
        let offset = effectiveOffset
        var hits: Set<String> = []
        for node in nodes {
            guard let base = layout[node.id] else { continue }
            let screen = CGPoint(
                x: centre.x + (base.x - centre.x) * scale + offset.width,
                y: centre.y + (base.y - centre.y) * scale + offset.height
            )
            if box.contains(screen) { hits.insert(node.id) }
        }
        return hits
    }

    func marqueeShape(_ box: CGRect) -> some View {
        Rectangle()
            .fill(Color.accentColor.opacity(0.12))
            .overlay(Rectangle().stroke(Color.accentColor, lineWidth: 1))
            .frame(width: box.width, height: box.height)
            .position(x: box.midX, y: box.midY)
            .allowsHitTesting(false)
    }

    var modeToggle: some View {
        Picker("Canvas tool", selection: $canvasMode) {
            Image(systemName: "hand.draw").tag(CanvasMode.pan)
            Image(systemName: "rectangle.dashed").tag(CanvasMode.marquee)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 96)
        .padding(8)
        .help("Drag empty space to pan, or marquee-select nodes")
    }
}
