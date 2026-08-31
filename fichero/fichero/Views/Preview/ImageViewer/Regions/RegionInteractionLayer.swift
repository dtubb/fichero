import SwiftUI

/// Stable palette for multi-selected regions (Daniel, 2026-08-29: N selected
/// rows highlight in DISTINCT colors). Keyed by the BOX index so a region
/// keeps its color while the selection around it changes. Outside the macOS
/// gate: the inspector's region rows use the same colors on every platform.
enum RegionPalette {
    static let colors: [Color] = [
        .blue, .orange, .green, .purple, .pink, .teal, .red, .indigo
    ]

    static func color(forBoxIndex index: Int) -> Color {
        colors[((index % colors.count) + colors.count) % colors.count]
    }
}

#if os(macOS)

/// The INTERACTIVE region layer over the Preview image: click-to-select,
/// ⇧-click to add, drag-a-selected-region to move, and the ephemeral
/// rubber-band marquees (add mode). Sits ABOVE `OCRGeometryOverlay`, which
/// deliberately stays a single inert Canvas — this layer builds views only
/// for the handful of SELECTED boxes and marquees, so the hundreds-of-boxes
/// perf fix is not regressed.
///
/// Event posture: pan is the NSScrollView's two-finger scroll (scrollWheel),
/// which a SwiftUI tap layer does not consume — so a full-frame TAP target is
/// safe here where a full-frame drag target would not be. Drags exist only
/// (a) inside a selected region (move) and (b) in add mode (rubber band).
struct RegionInteractionLayer: View {
    /// Displayed boxes with their FULL-list indices into the owning
    /// artifact's `ocr_geometry.boxes` — the index the engine addresses.
    let boxes: [(index: Int, box: OCRGeometryBox)]
    /// The FULL box list. Selection highlight reads through this, not the
    /// display set: the inspector's rows are LINE-level while the overlay may
    /// be displaying words, and a selected line must still light up.
    let allBoxes: [OCRGeometryBox]
    let visible: CGRect
    /// The artifact owning `boxes`; nil when only marquees are in play.
    let artifactId: String?
    let documentId: String
    /// Per-window ephemeral marquee seam (nil in hosts without WindowState).
    let marquees: PreviewMarqueeSelection?
    /// The source image's pixel size — recorded with each marquee so ▶ can
    /// denormalize into `image.crop_child`'s pixel coordinates.
    let imagePixelSize: CGSize?
    /// True while rubber-band add mode is armed.
    let isAddingRegion: Bool
    /// Commit a moved region: (full-list index, new normalized bbox).
    let onMoveCommit: (Int, [Double]) -> Void
    /// Save the drawn marquees as regions: (name, marquee index). An empty
    /// name saves them unnamed; a nil index means the WHOLE set (the
    /// right-click verb), a non-nil index just that one marquee (its badge).
    let onPromote: (String, Int?) -> Void
    /// Double-click a saved region box: (full-list index). The host decides
    /// whether that means opening the region's child node or zooming to it.
    let onOpenRegion: (Int) -> Void

    /// Sticky-tool + check-cycle seams (Daniel, 2026-08-30). Optional so
    /// headless hosts stay safe.
    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore?

    @State private var selection = RegionSelection.shared
    /// The armed "name this region" request (shared with the context-menu
    /// verb, which arms it without a badge of its own).
    @State private var naming = RegionNamingRequest.shared
    /// Live move drag: which box, and how far (view points).
    @State private var moveDrag: (index: Int, translation: CGSize)?
    /// Live rubber-band corners (view points).
    @State private var bandStart: CGPoint?
    @State private var bandCurrent: CGPoint?
    /// ⇧ held? Tracked via `onModifierKeysChanged` (pure SwiftUI — the §6b
    /// no-AppKit rule) because a tap gesture's value carries no modifiers.
    @State private var shiftHeld = false

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                marqueeRects(in: geo.size)
                selectedRegionRects(in: geo.size)
                if let rect = liveBandRect {
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                        .background(Color.accentColor.opacity(0.12))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .contentShape(Rectangle())
            .gesture(isAddingRegion || isWordSelecting ? bandGesture(in: geo.size) : nil)
            .gesture(tapGesture(in: geo.size))
            // Simultaneous, not competing: a double-click should SELECT the
            // region and then enter it, which is what the two gestures do
            // together. Racing them would cost the selection.
            .simultaneousGesture(openGesture(in: geo.size))
            .onModifierKeysChanged(mask: .shift) { _, new in
                shiftHeld = new.contains(.shift)
            }
        }
    }

    // MARK: - Drawing

    /// Selected regions, palette-colored, following a live move drag.
    /// Renders from the FULL list so a selection made in the inspector
    /// (line rows) lights up even while the overlay displays words.
    @ViewBuilder
    private func selectedRegionRects(in size: CGSize) -> some View {
        if artifactId != nil, selection.artifactId == artifactId {
            ForEach(selection.indices.filter { allBoxes.indices.contains($0) }, id: \.self) { index in
                let box = allBoxes[index]
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box.bbox, in: size, visible: visible
                ) {
                    let offset = moveDrag?.index == index
                        ? (moveDrag?.translation ?? .zero) : .zero
                    let color = RegionPalette.color(forBoxIndex: index)
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(color, lineWidth: 2)
                        .background(color.opacity(0.14))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX + offset.width, y: rect.minY + offset.height)
                        .gesture(moveGesture(for: (index: index, box: box), in: size))
                }
            }
        }
    }

    /// Ephemeral marquees: dashed, visually distinct from persisted regions;
    /// the marquee picked for deletion carries a solid accent stroke.
    @ViewBuilder
    private func marqueeRects(in size: CGSize) -> some View {
        if let marquees, marquees.documentId == documentId {
            ForEach(Array(marquees.rects.enumerated()), id: \.offset) { index, box in
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box, in: size, visible: visible
                ) {
                    let isPicked = marquees.selectedIndex == index
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(
                            Color.accentColor,
                            style: StrokeStyle(lineWidth: isPicked ? 2.5 : 1.5, dash: isPicked ? [] : [5])
                        )
                        .background(Color.accentColor.opacity(isPicked ? 0.18 : 0.08))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX, y: rect.minY)
                        .allowsHitTesting(false)
                    marqueeNameBadge(index: index, rect: rect)
                }
            }
        }
    }

    /// The "name it" affordance (Daniel, 2026-08-31: "or have an icon beside
    /// it, which lets you give it a name") — a pencil at the marquee's
    /// top-right corner. It is the ONLY hit-testable thing in the marquee
    /// layer: the rects themselves stay pass-through so the band and tap
    /// gestures below keep working.
    @ViewBuilder
    private func marqueeNameBadge(index: Int, rect: CGRect) -> some View {
        let side: CGFloat = 20
        Button {
            naming.arm(documentId: documentId, marqueeIndex: index)
        } label: {
            Image(systemName: "pencil.circle.fill")
                .font(.title3)
                .symbolRenderingMode(.palette)
                .foregroundStyle(Color.white, Color.accentColor)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Name this selection")
        .help("Name this selection and save it as a region")
        .frame(width: side, height: side)
        .offset(x: max(0, rect.maxX - side), y: max(0, rect.minY))
        .popover(isPresented: namingBinding(for: index)) {
            RegionNameField(request: naming) { name in
                // Read the target BEFORE clearing: the whole-set request
                // (nil) and this badge's own index are different verbs.
                let target = naming.marqueeIndex
                naming.clear()
                onPromote(name, target)
            }
        }
    }

    /// Presentation binding for marquee `index`'s naming popover. Dismissal
    /// (Esc, click-away) disarms the request rather than leaving it armed to
    /// re-open under the next marquee drawn.
    private func namingBinding(for index: Int) -> Binding<Bool> {
        Binding(
            get: { naming.anchors(documentId: documentId, index: index) },
            set: { presented in if !presented { naming.clear() } }
        )
    }

    private var liveBandRect: CGRect? {
        guard let start = bandStart, let current = bandCurrent else { return nil }
        return CGRect(
            x: min(start.x, current.x),
            y: min(start.y, current.y),
            width: abs(current.x - start.x),
            height: abs(current.y - start.y)
        )
    }

    // MARK: - Gestures

    /// Click = select; ⇧-click = add/toggle; click-away = deselect (regions
    /// AND marquees — the honest reading of "click-away clears").
    private func tapGesture(in size: CGSize) -> some Gesture {
        SpatialTapGesture().onEnded { value in
            // CHECK tool (Daniel, 2026-08-30): armed, a click checks the
            // nearest line — margin clicks included — cycling ✓ ✓✓ ✓✓✓ off.
            if windowState?.activeMarkupTool == .check {
                handleCheckTap(at: value.location, in: size)
                return
            }
            let additive = shiftHeld
            // Marquees first: they are drawn on top and are what the user
            // most recently made.
            if let marquees, marquees.documentId == documentId,
               let picked = RegionHitTesting.pick(
                   at: value.location, boxes: marquees.rects, in: size, visible: visible
               ) {
                marquees.selectedIndex = picked
                return
            }
            if let artifactId,
               let picked = RegionHitTesting.pick(
                   at: value.location, boxes: boxes.map { $0.box.bbox }, in: size, visible: visible
               ) {
                let fullIndex = boxes[picked].index
                if additive {
                    selection.toggle(fullIndex, artifactId: artifactId, documentId: documentId)
                } else {
                    selection.select(fullIndex, artifactId: artifactId, documentId: documentId)
                }
                marquees?.selectedIndex = nil
                return
            }
            // Empty ground: clear everything ephemeral.
            selection.clear()
            marquees?.clear()
        }
    }

    /// ENTER a region (Daniel, 2026-08-31: "double click on it to be taken to
    /// a new region"). Hit-tests the DISPLAYED boxes — what you can see is
    /// what you can enter (the visible-surface ruling) — and hands the host
    /// the full-list index; the host decides whether the box has a child node
    /// to open or is a bare geometry box to zoom to.
    private func openGesture(in size: CGSize) -> some Gesture {
        SpatialTapGesture(count: 2).onEnded { value in
            // The check tool owns the click while armed; a double-click there
            // is two cycles of the check, not a navigation.
            guard windowState?.activeMarkupTool != .check, artifactId != nil else { return }
            guard let picked = RegionHitTesting.pick(
                at: value.location, boxes: boxes.map { $0.box.bbox },
                in: size, visible: visible
            ) else { return }
            onOpenRegion(boxes[picked].index)
        }
    }

    /// Word-boundary marquee armed (Daniel, 2026-08-30, ruling 2)? The band
    /// then selects the WORD boxes it touches instead of adding a marquee.
    private var isWordSelecting: Bool {
        windowState?.activeMarkupTool == .wordSelect
    }

    /// Rubber-band drag (armed modes only — a full-frame drag target outside
    /// an armed mode would fight the platform): a new marquee in add mode, a
    /// word-box selection in word-select mode.
    private func bandGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                if bandStart == nil { bandStart = value.startLocation }
                bandCurrent = value.location
            }
            .onEnded { value in
                defer { bandStart = nil; bandCurrent = nil }
                let start = bandStart ?? value.startLocation
                guard let box = BoundingBoxGeometry.normalizedBox(
                    from: start, to: value.location, in: size, visible: visible
                ) else { return }
                if isWordSelecting {
                    selectWords(inBand: box)
                } else {
                    marquees?.add(
                        box, documentId: documentId, imagePixelSize: imagePixelSize
                    )
                }
            }
    }

    /// Select (⇧ = extend) the word boxes the band touched — they light via
    /// the shared `RegionSelection`, so Delete and the region verbs address
    /// them exactly the way the inspector's rows are addressed.
    private func selectWords(inBand band: [Double]) {
        guard let artifactId else { return }
        let hits = AnnotationWordSelection.wordIndices(inBand: band, boxes: allBoxes)
        guard !hits.isEmpty else {
            if !shiftHeld { selection.clear() }
            return
        }
        var remaining = hits[...]
        if !shiftHeld {
            selection.select(hits[0], artifactId: artifactId, documentId: documentId)
            remaining = hits.dropFirst()
        }
        for index in remaining where !selection.isSelected(index, in: artifactId) {
            selection.toggle(index, artifactId: artifactId, documentId: documentId)
        }
    }

    /// Drag a SELECTED region to move it; the bbox commits on mouse-up.
    private func moveGesture(
        for item: (index: Int, box: OCRGeometryBox), in size: CGSize
    ) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                moveDrag = (item.index, value.translation)
            }
            .onEnded { value in
                moveDrag = nil
                if let moved = RegionHitTesting.moved(
                    bbox: item.box.bbox, byViewDelta: value.translation,
                    in: size, visible: visible
                ) {
                    onMoveCommit(item.index, moved)
                }
            }
    }
}

extension RegionInteractionLayer {
    /// The line at this click's height (x ignored so a margin click counts),
    /// else a small square at the click. Cycles the saved check: none → ✓ →
    /// ✓✓ → ✓✓✓ → none, persisted as the rating annotation kind.
    func handleCheckTap(at point: CGPoint, in size: CGSize) {
        guard let annotationStore, let windowState else { return }
        let lines = allBoxes.filter { $0.level == "line" }
        var target: [Double]?
        for line in lines {
            if let rect = BoundingBoxGeometry.viewRect(
                normalized: line.bbox, in: size, visible: visible
            ), point.y >= rect.minY, point.y <= rect.maxY {
                target = line.bbox
                break
            }
        }
        if target == nil, size.width > 0, size.height > 0 {
            // No recognised line at that height: a small check box AT the
            // click, so unrecognised pages are checkable too.
            let normalized = BoundingBoxGeometry.normalizedBox(
                from: CGPoint(x: max(0, point.x - 8), y: max(0, point.y - 8)),
                to: CGPoint(x: point.x + 8, y: point.y + 8),
                in: size, visible: visible
            )
            target = normalized
        }
        guard let bbox = target else { return }
        let docId = documentId
        Task { @MainActor in
            // Cycle against the existing check on the SAME extent.
            let existing = annotationStore.annotations.first { annotation in
                annotation.kind == .rating
                    && (annotation.documentId == docId || annotation.pageId == docId)
                    && Self.sameExtent(annotation.regionRect, bbox)
            }
            if let existing {
                let next = (existing.rating ?? 1) + 1
                _ = await annotationStore.delete(id: existing.id)
                guard next <= 3 else { return }  // ✓✓✓ → clear
                _ = await annotationStore.addNote(
                    scope: .document(docId), text: "",
                    bbox: bbox, kind: .rating, rating: next
                )
            } else {
                // Coding v1 (ruling 4): pending tags ride a NEW check too —
                // a triple-check can carry a code.
                _ = await annotationStore.addNote(
                    scope: .document(docId), text: "",
                    bbox: bbox, kind: .rating, rating: 1,
                    tags: windowState.takePendingMarkupTags()
                )
            }
        }
    }

    static func sameExtent(_ lhs: [Double]?, _ rhs: [Double], tolerance: Double = 0.01) -> Bool {
        guard let lhs, lhs.count >= 4, rhs.count >= 4 else { return false }
        return zip(lhs.prefix(4), rhs.prefix(4)).allSatisfy { abs($0 - $1) < tolerance }
    }
}

#endif
