import SwiftUI

#if os(macOS)

/// The INTERACTIVE region layer over the Preview image: click-to-select,
/// ⇧-click to add, drag-a-selected-region to move, and the ephemeral
/// rubber-band marquees (add mode). Sits ABOVE `OCRGeometryOverlay`, which
/// deliberately stays a single inert Canvas — this layer builds views only
/// for the handful of SELECTED boxes and marquees, so the hundreds-of-boxes
/// perf fix is not regressed.
///
/// Event posture (2026-09-01): this layer owns NO gestures and is never
/// hit-testable (except the marquee name badges). Its clicks and drags come
/// from the AppKit image view via `PreviewPointerFeed`. The earlier
/// "a SwiftUI tap layer does not consume scrollWheel" belief was wrong on
/// macOS 26: a full-frame `contentShape` + gesture made the hosting view
/// claim hit-testing, and two-finger pan, pinch, and the page/rendition
/// swipes never reached the NSScrollView underneath.
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
    /// The rendition whose pixels are on screen, or nil for the node's own
    /// image. The check tool writes annotations from here, and an annotation
    /// with no frame is one that will be drawn over the wrong pixels
    /// (2026-09-03 — the same identity region geometry carries).
    var renditionId: String?
    /// True while rubber-band add mode is armed.
    let isAddingRegion: Bool
    /// Whether this layer draws the static selection highlight. False on the Mac image canvas,
    /// where the document overlay draws it in the same view and pass as its box (#5020). The live
    /// move-drag preview is still drawn here, because it follows the pointer.
    var drawsSelection: Bool = true
    /// The Shape tool in the Edit Segments mode: a drawn box becomes a segment at once
    /// (`SegmentEditingMode.shapeDrawsSegment`), not a marquee waiting to be named.
    var drawsSegments: Bool = false
    /// True while an ANNOTATION draw tool is armed (highlight/note/line/
    /// star). The band then becomes the annotation's box via `onAnnotate`
    /// (2026-09-02): these drags used to ride a full-frame SwiftUI
    /// DragGesture on `BoundingBoxOverlay` — the exact hit-claiming shape
    /// that starved the scroll view, and the one drag path left OFF the
    /// AppKit pointer feed, which is why its boxes could land away from the
    /// cursor while marquees landed true.
    var isAnnotating: Bool = false
    /// Finish an annotation band: normalized `[x, y, w, h]`.
    var onAnnotate: (([Double]) -> Void)?
    /// The image view's clicks and drags, normalized (2026-09-01). This
    /// layer owns NO gestures: a gesture-bearing SwiftUI view over the
    /// NSScrollView made the hosting view claim hit-testing, and two-finger
    /// pan, pinch and the swipes never reached the scroll view. nil in
    /// headless hosts (the layer is then display-only).
    var pointer: PreviewPointerFeed?
    /// Where the rubber band is laid out, in the host's top-left coordinates, each time it changes.
    /// Nil in the app. A hosted test reads the band here: walked in-process, SwiftUI's accessibility
    /// tree came back empty (2026-10-11 full run), so the identifier below never found the band (#5214).
    var onBandFrame: ((CGRect) -> Void)?
    /// Commit a moved region: (full-list index, new normalized bbox).
    let onMoveCommit: (Int, [Double]) -> Void
    /// Save the drawn marquees as regions: (name, marquee index). An empty
    /// name saves them unnamed; a nil index means the WHOLE set (the
    /// right-click verb), a non-nil index just that one marquee (its badge).
    let onPromote: (String, Int?) -> Void
    /// Double-click a saved region box: (full-list index). The host decides
    /// whether that means opening the region's child node or zooming to it.
    let onOpenRegion: (Int) -> Void
    /// Commit a Reshape: (full-list index, what was reshaped, its new points). Nil: no Reshape here.
    var onReshapeCommit: ((Int, SegmentShapes.Target, [[Double]]) -> Void)?
    /// What the Shape tool draws while editing segments (the window's `shapeKind`).
    var drawKind: SegmentShapes.DrawKind = .box
    /// Commit a drawn polygon or baseline: (its kind, its points). Nil: the Shape tool drags boxes only.
    var onDrawShapeCommit: ((SegmentShapes.DrawKind, [[Double]]) -> Void)?
    /// Commit a Knife stroke (K held): its points, in the page's fractions. Nil: no Knife here.
    var onKnifeCommit: (([[Double]]) -> Void)?
    /// What letting the selection go at a point (the page's fractions; ⌘ held?) would do (`segment-editor.reassign-by-drag`).
    /// Nil: a drag always moves.
    var lineDrop: (([Double], Bool) -> SegmentMover.Drop)?
    /// Make the selected lines the lines of this region (nil: the page's).
    var onReassignCommit: ((String?) -> Void)?

    /// Sticky-tool + check-cycle seams (Daniel, 2026-08-30). Optional so
    /// headless hosts stay safe.
    @Environment(WindowState.self) var windowState: WindowState?
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore?

    /// THE PANE'S selection, handed in (#5020): the layer never reaches for another pane's.
    let selection: RegionSelection
    /// The armed "name this region" request (shared with the context-menu
    /// verb, which arms it without a badge of its own).
    @State private var naming = RegionNamingRequest.shared
    /// Live move drag: which box, and how far (view points); where it began.
    @State private var moveDrag: (index: Int, translation: CGSize)?
    @State private var moveStart: CGPoint?
    /// What letting the move drag go here would do: a reassignment lights its region.
    @State private var moveDrop: SegmentMover.Drop?
    /// Live rubber-band corners (view points).
    @State private var bandStart: CGPoint?
    @State private var bandCurrent: CGPoint?
    /// ⌘ held as the band or lasso began: it selects regions (`segment-editor.select-marquee-lasso`).
    @State var bandCommand = false
    /// A live lasso (⌥-drag on empty page in Select): the loop so far, in the page's fractions.
    @State var lasso: [[Double]] = []
    /// ⇧ held? Tracked via `onModifierKeysChanged` (pure SwiftUI — the §6b
    /// no-AppKit rule) because a tap gesture's value carries no modifiers.
    @State private var shiftHeld = false
    /// ⌘ held, from the same pointer event.
    @State private var commandHeld = false
    /// Live Reshape: the box, what is reshaped, the point being dragged, and the points as they are now.
    @State var reshapeDrag: ReshapeDrag?
    /// Live Resize (#5215): the box, the handle pressed, and the box as it is now.
    @State var resizeDrag: BoxResize.Drag?
    /// The segment box a double-click opened, shown in its popover (#5414); nil when none is open.
    @State var segmentPopover: SegmentPopoverTarget?

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                // Display layer: never hit-testable, so every trackpad
                // gesture falls through to the NSScrollView beneath.
                ZStack(alignment: .topLeading) {
                    if drawsSelection { marqueeRects(in: geo.size) }  // else the document overlay does
                    selectedRegionRects(in: geo.size)
                    dropTargetRect(in: geo.size)
                    liveReshape(in: geo.size)
                    liveDrawing(in: geo.size)
                    liveKnife(in: geo.size)
                    liveLasso(in: geo.size)
                    liveSimplify(in: geo.size)
                    segmentNotice()
                    if let rect = liveBandRect {
                        // The one rubber band (#4601), not a dashed accent box.
                        RubberBand()
                            .frame(width: rect.width, height: rect.height)
                            // Measured INSIDE the offset, so the frame is where the band is drawn
                            // after the offset and the layer's alignment, not where layout put it.
                            .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { onBandFrame?($0) }
                            .offset(x: rect.minX, y: rect.minY)
                            .accessibilityElement().accessibilityIdentifier(Self.liveBandIdentifier)
                    }
                }
                .allowsHitTesting(false)
                // The ONE clickable thing: each marquee's name badge. A
                // 20pt button claims only its own square.
                marqueeBadges(in: geo.size)
                segmentPopoverAnchor(in: geo.size)
            }
            // TOP-LEADING, never the default centre (#5214): every child is placed by `.offset` from the
            // layer's origin, and a centred frame put the content's (smaller) bounds in the MIDDLE -- with
            // only the rubber band drawn, the band landed below and right of the pointer by half the gap.
            .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
            .onChange(of: pointer?.sequence) { _, _ in
                guard let event = pointer?.latest else { return }
                PreviewPointerProfile.handling(event.phase) { handlePointer(event, in: geo.size) }
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
            ForEach(selection.resolvedIndices(in: allBoxes).filter {
                drawsSelection || moveDrag?.index == $0
            }, id: \.self) { index in
                let box = allBoxes[index]
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box.bbox, in: size, visible: visible
                ) {
                    let offset = moveDrag?.index == index
                        ? (moveDrag?.translation ?? .zero) : .zero
                    // ONE color for selection (Daniel, 2026-08-31: "don't
                    // make them multicolored when selected"). The palette
                    // stays for the inspector's region ROWS, where color is
                    // identity; on the page, selection is selection.
                    let color = Color.accentColor
                    RoundedRectangle(cornerRadius: 2)
                        .stroke(color, lineWidth: 2)
                        .background(color.opacity(0.14))
                        .frame(width: rect.width, height: rect.height)
                        .offset(x: rect.minX + offset.width, y: rect.minY + offset.height)
                }
            }
        }
    }

    /// The region a drag of lines would reassign them to, lit while the drag is over it.
    @ViewBuilder
    private func dropTargetRect(in size: CGSize) -> some View {
        if case .reassign(let target?) = moveDrop,
           let box = allBoxes.first(where: { $0.segmentId == target }),
           let rect = BoundingBoxGeometry.viewRect(normalized: box.bbox, in: size, visible: visible) {
            RoundedRectangle(cornerRadius: 2)
                .stroke(Color.accentColor, lineWidth: 3)
                .frame(width: rect.width, height: rect.height)
                .offset(x: rect.minX, y: rect.minY)
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
                }
            }
        }
    }

    /// The badges alone, in their own hit-testable layer above the inert
    /// display layer (see `body`).
    @ViewBuilder
    private func marqueeBadges(in size: CGSize) -> some View {
        // Naming a marquee saves it as a region -- a write -- so the badge is part of the
        // segment-editing mode (#5114). Reading, a marquee is only a run scope.
        if isEditing, let marquees, marquees.documentId == documentId {
            ForEach(Array(marquees.rects.enumerated()), id: \.offset) { index, box in
                if let rect = BoundingBoxGeometry.viewRect(
                    normalized: box, in: size, visible: visible
                ) {
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
        // The popover is attached BEFORE the badge is placed, and the badge is placed with `position` (layout), not
        // `offset` (a drawing shift the popover cannot see): with `offset` the popover hung off the layer's top left
        // corner, not off the marquee's pencil.
        .popover(isPresented: namingBinding(for: index)) {
            RegionNameField(request: naming) { name in
                // Read the target BEFORE clearing: the whole-set request
                // (nil) and this badge's own index are different verbs.
                let target = naming.marqueeIndex
                naming.clear()
                onPromote(name, target)
            }
        }
        .position(x: max(0, rect.maxX - side) + side / 2, y: max(0, rect.minY) + side / 2)
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

    /// The rubber band's accessibility identifier: where it is drawn, read by a test the way a script reads it.
    static let liveBandIdentifier = "RegionLiveBand"

    private var liveBandRect: CGRect? {
        guard let start = bandStart, let current = bandCurrent else { return nil }
        return CGRect(
            x: min(start.x, current.x),
            y: min(start.y, current.y),
            width: abs(current.x - start.x),
            height: abs(current.y - start.y)
        )
    }
}

// MARK: - Gestures

extension RegionInteractionLayer {
    /// Where a normalized image point lands in this layer.
    private func layerPoint(_ normalized: CGPoint, in size: CGSize) -> CGPoint? {
        guard let rect = BoundingBoxGeometry.viewRect(
            normalized: [normalized.x, normalized.y, 0, 0], in: size, visible: visible
        ) else { return nil }
        return CGPoint(x: rect.minX, y: rect.minY)
    }

    /// The AppKit pointer, dispatched by phase. Mouse-down decides the verb
    /// (check, band, move, or click-select) exactly as the three former
    /// gestures did; drag and up continue whatever the down began.
    private func handlePointer(_ event: PreviewPointerEvent, in size: CGSize) {
        guard let point = layerPoint(event.point, in: size) else { return }
        shiftHeld = event.shift
        commandHeld = event.command
        // Edit Segments on ONE selected shape: Reshape takes the press, the drag and the release.
        // An armed Polygon or Baseline tool owns the click first (#6476): a point placed inside a selected region
        // was taken by Reshape and the region, not the drawing, got it.
        if handleKnife(event) || handleDrawShape(event, in: size) || handleReshape(event, in: size) { return }
        if handleLasso(event, at: point, in: size) { return }
        switch event.phase {
        case .pressed:
            handlePress(at: point, clickCount: event.clickCount, in: size)
        case .dragged:
            if bandStart != nil {
                bandCurrent = point
            } else if let drag = moveDrag, let start = moveStart {
                moveDrag = (drag.index, CGSize(width: point.x - start.x, height: point.y - start.y))
                moveDrop = lineDrop?([event.point.x, event.point.y], event.command)
            }
        case .released:
            if let start = bandStart {
                finishBand(from: start, to: point, in: size)
            } else if let drag = moveDrag {
                finishMove(drag, droppedAt: [event.point.x, event.point.y], command: event.command, in: size)
            }
        }
    }

    /// Mouse-down decides the verb: double-click enters, the check tool
    /// checks, an armed band mode starts a rubber band, a press on a selected
    /// box starts a move, anything else is a click-select.
    private func handlePress(at point: CGPoint, clickCount: Int, in size: CGSize) {
        if clickCount == 2 {
            // Double-click a MARQUEE names it (Daniel, 2026-09-02: the
            // pointer feed "feels off" — the pencil badge was the only way
            // in). Saved regions keep their select-then-enter double-click.
            if isEditing, let marquees, marquees.documentId == documentId,
               let picked = RegionHitTesting.pick(
                   at: point, boxes: marquees.rects, in: size, visible: visible
               ) {
                marquees.selectedIndex = picked
                naming.arm(documentId: documentId, marqueeIndex: picked)
                return
            }
            // Select, THEN enter — the two verbs of a double-click.
            handleTap(at: point, in: size)
            handleOpen(at: point, in: size)
            return
        }
        if windowState?.activeMarkupTool == .check {
            handleCheckTap(at: point, in: size)
            return
        }
        if isAddingRegion || isWordSelecting || isAnnotating {
            bandStart = point
            bandCurrent = point
            return
        }
        if let hit = selectedBoxIndex(at: point, in: size),
           SegmentEditingMode.pressStartsMove(isEditing: isEditing, onSelectedBox: true, shift: shiftHeld) {
            moveDrag = (hit, .zero)
            moveStart = point
            return
        }
        // Select tool on empty ground: a DRAG band-selects the boxes it
        // sweeps (2026-09-02, select-by-default); a plain click still
        // resolves as a tap when the band comes back degenerate.
        if isBandSelecting, !hitsAnything(at: point, in: size) {
            bandStart = point
            bandCurrent = point
            bandCommand = commandHeld
            return
        }
        handleTap(at: point, in: size)
    }

    /// The select tool armed (the DEFAULT since 2026-09-02)?
    var isBandSelecting: Bool {
        windowState?.activeMarkupTool == .select
    }

    /// Anything clickable under the point — a marquee or a displayed box.
    func hitsAnything(at location: CGPoint, in size: CGSize) -> Bool {
        if let marquees, marquees.documentId == documentId,
           RegionHitTesting.pick(
               at: location, boxes: marquees.rects, in: size, visible: visible
           ) != nil {
            return true
        }
        return RegionHitTesting.pick(
            at: location, boxes: boxes.map { $0.box.bbox }, in: size, visible: visible
        ) != nil
    }

    /// Click = select; ⇧-click = add/toggle; click-away = deselect (regions
    /// AND marquees — the honest reading of "click-away clears").
    func handleTap(at location: CGPoint, in size: CGSize) {
        let additive = shiftHeld
        // Marquees first: they are drawn on top and are what the user
        // most recently made.
        if let marquees, marquees.documentId == documentId,
           let picked = RegionHitTesting.pick(
               at: location, boxes: marquees.rects, in: size, visible: visible
           ) {
            marquees.selectedIndex = picked
            return
        }
        if let artifactId,
           let picked = RegionHitTesting.pick(
               at: location, boxes: boxes.map { $0.box.bbox }, in: size, visible: visible
           ) {
            let fullIndex = boxes[picked].index
            if additive {
                selection.toggle(fullIndex, artifactId: artifactId, documentId: documentId, in: allBoxes)
            } else {
                selection.select(fullIndex, artifactId: artifactId, documentId: documentId, in: allBoxes)
            }
            marquees?.selectedIndex = nil
            return
        }
        // Empty ground: clear everything ephemeral.
        selection.clear()
        marquees?.clear()
    }

    /// ENTER a region (Daniel, 2026-08-31: "double click on it to be taken to
    /// a new region"). Hit-tests the DISPLAYED boxes — what you can see is
    /// what you can enter (the visible-surface ruling) — and hands the host
    /// the full-list index; the host decides whether the box has a child node
    /// to open or is a bare geometry box to zoom to.
    private func handleOpen(at location: CGPoint, in size: CGSize) {
        // The check tool owns the click while armed; a double-click there
        // is two cycles of the check, not a navigation.
        guard windowState?.activeMarkupTool != .check, artifactId != nil else { return }
        guard let picked = RegionHitTesting.pick(
            at: location, boxes: boxes.map { $0.box.bbox },
            in: size, visible: visible
        ) else { return }
        if !openSegmentPopover(for: boxes[picked].box) { onOpenRegion(boxes[picked].index) }
    }

    /// A SELECTED box under the point (full-list index), for move drags.
    private func selectedBoxIndex(at location: CGPoint, in size: CGSize) -> Int? {
        guard let artifactId, selection.artifactId == artifactId else { return nil }
        let candidates = selection.resolvedIndices(in: allBoxes)
        guard let picked = RegionHitTesting.pick(
            at: location, boxes: candidates.map { allBoxes[$0].bbox }, in: size, visible: visible
        ) else { return nil }
        return candidates[picked]
    }

    /// Word-boundary marquee armed (Daniel, 2026-08-30, ruling 2)? The band
    /// then selects the WORD boxes it touches instead of adding a marquee.
    private var isWordSelecting: Bool {
        windowState?.activeMarkupTool == .wordSelect
    }

    /// Rubber band released: a new marquee in add mode, a word-box selection
    /// in word-select mode, a region band-select with the select tool. A
    /// degenerate (tap-sized) band resolves as the click it really was.
    private func finishBand(from start: CGPoint, to end: CGPoint, in size: CGSize) {
        defer { bandStart = nil; bandCurrent = nil }
        guard let box = BoundingBoxGeometry.normalizedBox(
            from: start, to: end, in: size, visible: visible
        ) else {
            // The select tool's degenerate band IS the empty-ground click —
            // it must still deselect, or click-away stops working.
            if isBandSelecting, !isWordSelecting, !isAddingRegion {
                handleTap(at: start, in: size)
            }
            return
        }
        if isAnnotating {
            onAnnotate?(box)
        } else if isWordSelecting {
            selectWords(inBand: box)
        } else if isAddingRegion {
            marquees?.add(
                box, documentId: documentId, imagePixelSize: imagePixelSize
            )
            if drawsSegments, let marquees, !marquees.isEmpty {
                // The marquee just drawn, promoted through the ONE region-making path.
                onPromote("", marquees.count - 1)
            }
        } else {
            selectRegions(inBand: box)
        }
    }

    /// Select (⇧ = extend) every DISPLAYED box the band holds mostly (over half), at the level being edited —
    /// lines, or regions with ⌘ (`segment-editor.select-marquee-lasso`) — addressed the way a click-select is.
    private func selectRegions(inBand band: [Double]) {
        selectRegions(inLoop: SegmentSelectionGestures.loop(ofBand: band))
    }

    /// Select (⇧ = extend) every DISPLAYED box the loop holds mostly, at the level being edited.
    func selectRegions(inLoop loop: [[Double]]) {
        guard let artifactId else { return }
        let shown = boxes.map { SegmentSelectionGestures.Box(index: $0.index, bbox: $0.box.bbox, level: $0.box.level) }
        let hits = SegmentSelectionGestures.inside(
            loop, boxes: shown, level: SegmentSelectionGestures.level(of: shown, commandHeld: bandCommand)
        )
        guard !hits.isEmpty else {
            if !shiftHeld { selection.clear() }
            return
        }
        var remaining = hits[...]
        if !shiftHeld {
            selection.select(hits[0], artifactId: artifactId, documentId: documentId, in: allBoxes)
            remaining = hits.dropFirst()
        }
        for index in remaining where !selection.isSelected(index, in: artifactId) {
            selection.toggle(index, artifactId: artifactId, documentId: documentId, in: allBoxes)
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
            selection.select(hits[0], artifactId: artifactId, documentId: documentId, in: allBoxes)
            remaining = hits.dropFirst()
        }
        for index in remaining where !selection.isSelected(index, in: artifactId) {
            selection.toggle(index, artifactId: artifactId, documentId: documentId, in: allBoxes)
        }
    }

    /// A SELECTED region was dragged; the bbox commits on mouse-up. A drag
    /// too small to mean anything leaves the region where it was. Lines let go
    /// on another region (or none) are reassigned instead, their shapes left
    /// where they are (`segment-editor.reassign-by-drag`).
    private func finishMove(
        _ drag: (index: Int, translation: CGSize), droppedAt point: [Double], command: Bool, in size: CGSize
    ) {
        defer { moveDrag = nil; moveStart = nil; moveDrop = nil }
        guard allBoxes.indices.contains(drag.index),
              abs(drag.translation.width) >= 2 || abs(drag.translation.height) >= 2 else { return }
        if case .reassign(let target) = lineDrop?(point, command) {
            onReassignCommit?(target)
            return
        }
        guard let moved = RegionHitTesting.moved(
                  bbox: allBoxes[drag.index].bbox, byViewDelta: drag.translation,
                  in: size, visible: visible
              ) else { return }
        onMoveCommit(drag.index, moved)
    }
}

extension RegionInteractionLayer {
    /// The ENTIRE line at this click's height (Daniel, 2026-09-04: the check
    /// applies to the full line box, one gesture; x ignored so a margin
    /// click counts) — and on a page with no recognised line, a full-width
    /// band one line tall, never a private 16pt square. Cycles the saved
    /// check: none → ✓ → ✓✓ → ✓✓✓ → none, persisted as the rating kind.
    func handleCheckTap(at point: CGPoint, in size: CGSize) {
        guard let annotationStore, let windowState,
              size.height > 0, visible.height > 0 else { return }
        let normalizedY = visible.minY + Double(point.y / size.height) * visible.height
        let bbox = RegionHitTesting.checkTarget(
            atNormalizedY: normalizedY,
            lines: allBoxes.filter { $0.level == "line" }.map(\.bbox)
        )
        let docId = documentId
        let frame = renditionId
        Task { @MainActor in
            // Cycle against the existing check on the SAME extent.
            let existing = annotationStore.annotations.first { annotation in
                annotation.kind == .rating
                    && (annotation.documentId == docId || annotation.pageId == docId)
                    // Same PLACE means same frame too: a check on the deskewed
                    // rendition and one on the base page can share a rect and
                    // still be different marks (2026-09-03).
                    && annotation.renditionId == frame
                    && Self.sameExtent(annotation.regionRect, bbox)
            }
            if let existing {
                let next = AnnotationCheckCycle.next(existing.rating ?? 1)
                _ = await annotationStore.delete(id: existing.id)
                guard let next else { return }  // ✓✓✓ → clear
                _ = await annotationStore.addNote(
                    scope: .document(docId), text: "",
                    bbox: bbox, renditionId: frame, kind: .rating, rating: next
                )
            } else {
                // Coding v1 (ruling 4): pending tags ride a NEW check too —
                // a triple-check can carry a code.
                _ = await annotationStore.addNote(
                    scope: .document(docId), text: "",
                    bbox: bbox, renditionId: frame, kind: .rating,
                    rating: AnnotationCheckCycle.next(nil) ?? 1,
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
