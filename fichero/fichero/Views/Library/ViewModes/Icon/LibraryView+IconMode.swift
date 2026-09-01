import FicheroAPIClient
import SwiftUI

// MARK: - Icons View (Grid)

extension LibraryView {
    /// Grid-slot bounds for one icon tile (#4281). The tile's real footprint
    /// is `DocumentThumbnailView.wellWidth * scale` (100pt at scale 1) — the
    /// old hardcoded 120…150 slot was up to 1.5 tiles wide, so default-size
    /// tiles sat in visibly double-width cells. The slot now hugs the tile
    /// (+8pt breathing room, +16pt stretch allowance) so one tile = one
    /// column at every scale. Pure so the view-settings tests pin it.
    nonisolated static func iconGridItemBounds(scale: Double) -> (min: CGFloat, max: CGFloat) {
        let tile = DocumentThumbnailView.wellWidth * CGFloat(scale)
        let minimum = max(70, tile + 8)
        return (min: minimum, max: minimum + 16)
    }

    /// The scale the grid draws at RIGHT NOW: the in-flight pinch value when
    /// a gesture is live, the persisted one otherwise.
    private var effectiveIconScale: Double { liveIconScale ?? iconViewScale }

    var iconsView: some View {
        let (itemMin, itemMax) = Self.iconGridItemBounds(scale: effectiveIconScale)
        // Parsed ONCE per render, not twice per tile (2026-08-31 perf): the
        // raw @AppStorage string was re-split into a Set inside the ForEach
        // for every document, on both the identity and the thumbnail.
        let showsName = LibraryRowAttribute.set(from: rowAttributesRaw).contains(.name)
        return GeometryReader { geometry in
            // Clamp pinch max so a single thumbnail never exceeds the visible
            // grid width. In the wide content grid this lets us zoom way in;
            // in a narrow sidebar grid the ceiling stays small. Cell width is
            // 100 * scale + ~16 padding, so max ≈ (width - 32) / 100.
            let pinchMax = max(1.0, min(5.0, Double((geometry.size.width - 32) / 100)))
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: itemMin, maximum: itemMax))],
                        alignment: .center,
                        spacing: 20
                    ) {
                        if isShowingEntitiesCollection {
                            ForEach(filteredEntities, id: \.stableInspectorId) { entity in
                                let entityId = entitySelectionId(for: entity)
                                EntityThumbnailView(
                                    entity: entity,
                                    isSelected: selection.contains(entityId),
                                    secondaryText: entityTileSecondaryText(for: entity),
                                    kindStyle: entityTileKindStyle(for: entity),
                                    selectedTint: selectionTint,
                                    scale: CGFloat(effectiveIconScale)
                                )
                                .id(entityId)
                                .onTapGesture(count: 2) {
                                    handleEntityDoubleClick(entity)
                                }
                                .onTapGesture {
                                    handleEntityTap(entity)
                                }
                                // Minimal parity with document tiles (#4160):
                                // right-click offers Open — the same action
                                // double-click performs.
                                .contextMenu {
                                    Button {
                                        handleEntityDoubleClick(entity)
                                    } label: {
                                        Label("Open", systemImage: "arrow.up.forward.square")
                                    }
                                }
                            }
                        } else {
                            ForEach(filteredDocuments) { doc in
                                LibraryIconCell(
                                    identity: IconCellIdentity(
                                        document: doc,
                                        scale: effectiveIconScale,
                                        isRenaming: renamingDocumentId == doc.id,
                                        showsName: showsName,
                                        searchHit: searchRowHits[doc.id]
                                    ),
                                    isSelected: selection.contains(doc.id),
                                    tint: selectionTint
                                ) {
                                    DocumentThumbnailView(
                                        document: doc,
                                        isSelected: selection.contains(doc.id),
                                        selectedTint: selectionTint,
                                        scale: CGFloat(effectiveIconScale),
                                        isRenaming: renamingDocumentId == doc.id,
                                        editingName: $editingName,
                                        onCommitRename: commitRename,
                                        onCancelRename: cancelRename,
                                        showsName: showsName
                                    )
                                    // The relevance number, same value and
                                    // same format list view shows on the row's
                                    // right edge (Daniel, 2026-09-01). Inside
                                    // the cell's content so `.equatable()`
                                    // governs it through `IconCellIdentity`.
                                    .overlay(alignment: .topTrailing) {
                                        if let hit = searchRowHits[doc.id] {
                                            SearchRelevanceBadge(score: hit.score)
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 1)
                                                .background(.thinMaterial, in: Capsule())
                                                .padding(4)
                                        }
                                    }
                                }
                                .equatable()
                                .id(doc.id)
                                .iconTileFrame(id: doc.id, in: "libraryIconGrid", model: marqueeModel)
                                .draggable(libraryItemDrag(for: doc)) {
                                    TileDragPreview(document: doc)
                                }
                                // Folder cells are real drop targets (#4124):
                                // only the hovered folder highlights, and the
                                // drop moves INTO it — not the viewed folder.
                                .modifier(LibraryFolderCellDrop(
                                    acceptsDrop: doc.acceptsItemDrops,
                                    onDropProviders: { providers in
                                        handleFolderCellDrop(providers, into: doc)
                                    }
                                ))
                                .onTapGesture(count: 2) {
                                    handleDoubleClick(doc)
                                }
                                .onTapGesture {
                                    handleTap(doc)
                                    onRequestFocus()
                                }
                                // Menu built at OPEN, not per render (#4544).
                                .contextMenu { SidebarDeferredMenuContent { documentContextMenu(for: doc) } }
                                .onAppear {
                                    scheduleThumbnailPrefetch(around: doc.id)
                                }
                            }
                        }
                    }
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    // INSIDE the scroll content, so the probe's superview
                    // chain reaches the NSScrollView autoscroll drives. As a
                    // `.background` on the ScrollView it would be a sibling
                    // and find the wrong one (or none).
                    .background(marqueeScrollProbe)
                }
                .coordinateSpace(name: "libraryIconGrid")
                // No `onPreferenceChange` here any more (2026-09-01): each
                // tile writes its own frame into the marquee box from
                // `iconTileFrame`, so there is no N-way dictionary reduce and
                // no N-entry equality diff on every layout pass. See that
                // modifier for what the preference was actually costing.
                // Click in the gutter/empty space deselects, like Finder
                // (#4160). Tile taps win — their gestures are deeper.
                .onTapGesture {
                    // A gutter click is still a click IN THIS PANE, so it
                    // claims focus the way a tile click does (2026-09-01). It
                    // did not, so clicking empty library space after clicking
                    // the preview left `paneFocusHint` on the preview and ⌘A
                    // kept routing there — the same missing claim #4436 fixed
                    // for the Table, in the one mode Daniel actually uses.
                    onRequestFocus()
                    apply(SelectionGrammar.clear())
                }
                // RUBBER BAND (Daniel's Finder ruling, 2026-08-09): a drag
                // that starts in the gutter sweeps a rect; intersecting
                // tiles feed SelectionGrammar.marquee LIVE (⇧/⌘ add, plain
                // replaces, an empty plain sweep clears). Tiles' own
                // .draggable wins on the tiles, so the marquee can only
                // begin on empty space — exactly Finder.
                .simultaneousGesture(
                    DragGesture(minimumDistance: 4, coordinateSpace: .named("libraryIconGrid"))
                        .onChanged { value in
                            beginMarqueeSweepIfNeeded(startingAt: value.startLocation)
                            marqueeModel.pointerViewport = value.location
                            updateMarqueeSweep()
                        }
                        .onEnded { _ in
                            marqueeModel.endSweep()
                        }
                )
                .overlay(alignment: .topLeading) {
                    MarqueeOverlayHost(model: marqueeModel)
                }
                // Right-click on empty library area → Import (#4449, third
                // of the three affordances). Tile-level context menus
                // (above) win over this one; it only fires on the gutter.
                // The shared builder, not a second copy — `emptyState`
                // mounts the SAME menu, and this gutter is only on screen
                // once the library already has rows.
                .contextMenu { libraryEmptyAreaImportMenu }
                // In icon mode, ScrollView may consume arrow keys for scrolling first.
                // Handle them at this level so keyboard selection always works.
                // NOTE: these deliberately DUPLICATE the body-level handlers in
                // LibraryView+KeyboardShortcuts (#4160 audit G12): the inner
                // set wins the key first; keep the two in sync when adding
                // directions (home/end added below to match).
                .onKeyPress(.upArrow, phases: .down) { _ in
                    handleArrowKey(direction: .upDir)
                }
                .onKeyPress(.downArrow, phases: .down) { _ in
                    handleArrowKey(direction: .down)
                }
                .onKeyPress(.leftArrow, phases: .down) { _ in
                    handleArrowKey(direction: .left)
                }
                .onKeyPress(.rightArrow, phases: .down) { _ in
                    handleArrowKey(direction: .right)
                }
                .onKeyPress(.pageUp, phases: .down) { _ in
                    handleArrowKey(direction: .pageUp)
                }
                .onKeyPress(.pageDown, phases: .down) { _ in
                    handleArrowKey(direction: .pageDown)
                }
                .onKeyPress(.home, phases: .down) { _ in
                    handleArrowKey(direction: .home)
                }
                .onKeyPress(.end, phases: .down) { _ in
                    handleArrowKey(direction: .end)
                }
                #if os(macOS)
                .onMoveCommand { direction in
                    handleMoveCommand(direction)
                }
                #endif
                // .focusable() here so the .onKeyPress handlers above receive
                // arrow keys (ScrollView would otherwise swallow them). But
                // the default focus ring draws around this whole scroll area
                // at the top of the view — visually misleading since the
                // "focus" semantically belongs to the selected cell.
                // `.focusEffectDisabled()` suppresses the container ring;
                // per-cell focus is already expressed via the accent overlay
                // in DocumentThumbnailView based on `isSelected` (#575).
                .focusable()
                .focusEffectDisabled()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.leading, browserLeadingInset)
                // #4589 (Daniel): load a folder's thumbnails when it OPENS,
                // bounded, instead of lazy-loading on scroll — the grid
                // jumped as rows arrived. The per-row look-ahead prefetch
                // stays as the catch-up path for folders above the cap.
                .task(id: "\(folderId ?? "root")-\(filteredDocuments.count)") {
                    prefetchFolderThumbnails()
                }
                // Pinch-to-zoom on the trackpad resizes icons live, like
                // Finder's icon view. Clamped 0.5–2.5x to match the toolbar
                // +/- buttons' usable range; persisted via @AppStorage on
                // iconViewScale so the scale survives relaunch.
                // Round to 0.05 steps so LazyVGrid relayouts a few times per
                // gesture instead of every magnification tick — eliminates the
                // jitter without losing perceived smoothness (#782). Max raised
                // 2.5 → 5.0 to match the toolbar +/- range so users can really
                // zoom in on stamps/handwriting (same rationale as #604).
                .gesture(
                    MagnificationGesture()
                        .onChanged { magnitude in
                            let candidate = pinchBaseScale * magnitude
                            let clamped = max(0.5, min(pinchMax, candidate))
                            // 0.1 steps while LIVE (relayout is the cost), and
                            // no UserDefaults write until the hands come off.
                            let stepped = (clamped * 10).rounded() / 10
                            if stepped != effectiveIconScale {
                                liveIconScale = stepped
                            }
                        }
                        .onEnded { _ in
                            if let landed = liveIconScale {
                                // The ONE persisted write per gesture, at the
                                // fine 0.05 grain the toolbar buttons use.
                                iconViewScale = (landed * 20).rounded() / 20
                                liveIconScale = nil
                            }
                            pinchBaseScale = iconViewScale
                        }
                )
                .onChange(of: geometry.size.width) { _, newWidth in
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = newWidth - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))
                    // If the pane just shrank (e.g. a sidebar panel), also
                    // shrink iconViewScale so a single icon can't be wider
                    // than its container.
                    let newPinchMax = max(1.0, min(5.0, Double((newWidth - 32) / 100)))
                    if iconViewScale > newPinchMax {
                        iconViewScale = newPinchMax
                        pinchBaseScale = newPinchMax
                    }
                }
                .onAppear {
                    let cellWidth = CGFloat(120 * iconViewScale) + 20
                    let availableWidth = geometry.size.width - 32
                    gridColumnCount = max(1, Int(availableWidth / cellWidth))

                    // Restored-from-launch selection scroll (#808). On launch
                    // the previous selection is restored but the LazyVGrid
                    // boots scrolled to the top — selected item is offscreen.
                    // Defer one tick so LazyVGrid materialises enough cells
                    // for scrollTo to find the id, then center on it.
                    if let id = orderedPrimarySelectionId {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                proxy.scrollTo(id, anchor: .center)
                            }
                        }
                    }
                }
                .onChange(of: listScrollTarget) { _, id in
                    guard let id else { return }
                    // Arrow-key nav: minimal scroll. anchor: nil = "scroll just
                    // enough to make visible, no-op if already visible." This
                    // is what fixes #769 — earlier code used .center which
                    // recentered on every keypress.
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(id, anchor: nil)
                    }
                    listScrollTarget = nil
                }
                .onChange(of: listScrollCenterTarget) { _, id in
                    guard let id else { return }
                    // Double-click / layout-change: force center so the user
                    // can find the item they just opened in the now-shrunken
                    // grid pane.
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(id, anchor: .center)
                    }
                    listScrollCenterTarget = nil
                }
                // PDF preview scrolling → selection changes externally
                // (via syncGridSelectionToPDFPage). Without this watcher,
                // the row highlight moved but the viewport didn't follow,
                // so the selected page could end up off-screen below or
                // above what's rendered. (#929) Watches the whole Set and
                // follows the ORDERED cursor (#4160) — watching the Set's
                // hash-first element could miss changes entirely when the
                // hash-first id stayed the same.
                .onChange(of: selection) { _, _ in
                    // NOT while a rubber band is live (2026-08-31): every hit
                    // set change re-entered here and ANIMATED the viewport to
                    // the sweep's primary id — the scroll view relaid out and
                    // re-reported every tile frame per tick, which is what
                    // made drawing a selection "super slow", and it yanked the
                    // grid out from under the pointer. Autoscroll owns the
                    // viewport during a sweep.
                    guard marqueeModel.anchorContent == nil else { return }
                    guard let id = orderedPrimarySelectionId else { return }
                    withAnimation(.easeInOut(duration: 0.15)) {
                        proxy.scrollTo(id, anchor: nil)
                    }
                }
                .onChange(of: thumbnailPrefetchKey) { _, _ in
                    resetThumbnailPrefetch()
                }
                .onDisappear {
                    thumbnailPrefetchTask?.cancel()
                }
            }
        }
    }

    // MARK: - Rubber band (2026-08-31: "drawing selection in library is
    // super slow, and if you draw a marquee so that it should scroll, it
    // should scroll"). The sweep runs in CONTENT space — viewport point plus
    // the scroll offset — so autoscrolling under a still pointer moves the
    // band's far edge without dragging its anchor along.

    /// The AppKit probe, or nothing where there is no AppKit.
    @ViewBuilder
    private var marqueeScrollProbe: some View {
        #if os(macOS)
        MarqueeScrollProbe(model: marqueeModel).frame(width: 0, height: 0)
        #else
        Color.clear.frame(width: 0, height: 0)
        #endif
    }

    /// Open a sweep, if this drag is allowed to start one. The gutter-only
    /// claim, ENFORCED (#34, Daniel: ⌘-click add "sometimes deselects") — a
    /// click ON a tile that wiggles past 4pt used to start a degenerate sweep
    /// that re-applied the toggle the tile's own tap had just made. A sweep
    /// may only BEGIN where no tile is; once live it continues anywhere.
    func beginMarqueeSweepIfNeeded(startingAt start: CGPoint) {
        guard marqueeModel.anchorContent == nil,
              LibraryMarquee.startsInGutter(start, frames: marqueeModel.tileFrames)
        else { return }
        let offset = marqueeModel.scrollOffsetY
        marqueeModel.anchorContent = CGPoint(x: start.x, y: start.y + offset)
        // The frame index, built ONCE here — hit-testing no longer depends on
        // the preference storm the grid emits while it re-renders.
        marqueeModel.contentFrames = marqueeModel.tileFrames.mapValues {
            $0.offsetBy(dx: 0, dy: offset)
        }
        marqueeModel.baseSelection = selection
        marqueeModel.lastHits = []
        marqueeModel.lastHitRect = nil
        startMarqueeAutoScroll()
    }

    /// One sweep tick: redraw the band, set the autoscroll velocity, and
    /// re-test tiles only when the band actually moved.
    func updateMarqueeSweep() {
        guard let anchor = marqueeModel.anchorContent else { return }
        let offset = marqueeModel.scrollOffsetY
        let pointer = marqueeModel.pointerViewport
        let contentRect = LibraryMarquee.rect(
            from: anchor,
            to: CGPoint(x: pointer.x, y: pointer.y + offset)
        )
        // The band is the ONLY thing that redraws per tick: the overlay host
        // is the sole reader of this observed property.
        marqueeModel.rect = contentRect.offsetBy(dx: 0, dy: -offset)
        // The edge zone is measured against the band the pointer can actually
        // occupy — the viewport MINUS the pane head and the bottom action bar,
        // which SwiftUI applies to this scroll view as content insets. Passing
        // the raw viewport put both zones under chrome, which is why the sweep
        // reached the visible edge and nothing scrolled.
        marqueeModel.autoScrollVelocity = LibraryMarquee.autoScrollVelocity(
            pointerY: pointer.y,
            viewportHeight: marqueeModel.viewportHeight,
            topInset: marqueeModel.viewportTopInset,
            bottomInset: marqueeModel.viewportBottomInset
        )
        // Throttle 1 — a mouse reports far finer than a tile is wide, and an
        // O(tiles) intersection sweep per sub-pixel tick is the slowness.
        guard LibraryMarquee.shouldRecomputeHits(
            from: marqueeModel.lastHitRect,
            to: contentRect
        ) else { return }
        marqueeModel.lastHitRect = contentRect
        let hits = LibraryMarquee.hitIds(in: marqueeModel.contentFrames, rect: contentRect)
        // Throttle 2 — selection is written only when MEMBERSHIP changes, so
        // the grid re-renders when a tile enters or leaves the band and never
        // per pixel (HARD rule: no wholesale list re-render).
        guard hits != marqueeModel.lastHits else { return }
        marqueeModel.lastHits = hits
        apply(SelectionGrammar.marquee(
            ids: hits,
            selection: marqueeModel.baseSelection ?? selection,
            modifiers: currentSelectionModifiers
        ))
    }

    /// Finder's edge autoscroll: while the pointer sits within ~24pt of the
    /// viewport's top or bottom, the grid scrolls that way and the band keeps
    /// growing. One ticker for the whole drag — it idles at velocity 0 rather
    /// than being torn down and rebuilt as the pointer crosses the zone.
    private func startMarqueeAutoScroll() {
        marqueeModel.autoScrollTask?.cancel()
        marqueeModel.autoScrollTask = Task { @MainActor in
            while !Task.isCancelled, marqueeModel.anchorContent != nil {
                try? await Task.sleep(for: .milliseconds(16))
                guard !Task.isCancelled, marqueeModel.anchorContent != nil else { return }
                let velocity = marqueeModel.autoScrollVelocity
                // Parked at either end of the document: nothing to extend.
                guard velocity != 0, marqueeModel.autoScroll(by: velocity) != 0 else { continue }
                updateMarqueeSweep()
            }
        }
    }

    private func resetThumbnailPrefetch() {
        prefetchedThumbnailIds.removeAll()
        thumbnailPrefetchTask?.cancel()
        thumbnailPrefetchTask = nil
    }

    // Internal (not private): the list view prefetches with the same window
    // from ITS rows' onAppear (#4160) — list rows previously fetched one at a
    // time on scroll, so every scroll showed skeleton churn. The table's name
    // cell joins them now that it renders thumbnails too (#4202).
    /// Prefetch the WHOLE open folder's thumbnails, front to back, capped
    /// (#4589). Runs once per folder/document-set through the same
    /// storage-service pipeline (6-wide concurrency) and the same
    /// `prefetchedThumbnailIds` ledger the scroll look-ahead uses, so the two
    /// paths never double-fetch. Its own task variable — a scroll prefetch
    /// must not cancel the folder sweep.
    func prefetchFolderThumbnails() {
        // ponytail: 600 covers every Marshall diary (max 204 pages) with
        // headroom; beyond the cap the scroll look-ahead still catches up.
        let cap = 600
        guard !isShowingEntitiesCollection else { return }
        let imageIds = filteredDocuments.prefix(cap)
            .filter {
                DocumentThumbnailKind.forDocument($0).fetchesStorageThumbnail
                    && !prefetchedThumbnailIds.contains($0.id)
            }
            .map(\.id)
        guard !imageIds.isEmpty,
              let storageService = scopedLibraryReference?.storageService else { return }
        prefetchedThumbnailIds.formUnion(imageIds)
        folderThumbnailPrefetchTask?.cancel()
        folderThumbnailPrefetchTask = Task {
            await storageService.prefetchThumbnails(imageIds)
        }
    }

    func scheduleThumbnailPrefetch(around documentId: String) {
        guard !isShowingEntitiesCollection,
              let index = documentIndexById[documentId] else { return }

        let behind = max(gridColumnCount * 2, 8)
        let ahead = max(gridColumnCount * 8, 24)
        let start = max(0, index - behind)
        let end = min(filteredDocuments.count, index + ahead)
        // Prefetch exactly what a thumbnail well will fetch: folders draw a
        // symbol and text documents draw their preview, so neither hits
        // storage — but PDFs and pages do, and the old `.image`-only filter
        // left them fetching one per row on scroll (#4202).
        let imageIds = filteredDocuments[start..<end]
            .filter {
                DocumentThumbnailKind.forDocument($0).fetchesStorageThumbnail
                    && !prefetchedThumbnailIds.contains($0.id)
            }
            .map(\.id)
        guard !imageIds.isEmpty,
              let storageService = scopedLibraryReference?.storageService else { return }

        prefetchedThumbnailIds.formUnion(imageIds)
        thumbnailPrefetchTask?.cancel()
        thumbnailPrefetchTask = Task {
            await storageService.prefetchThumbnails(imageIds)
        }
    }

    private func entityTileKindStyle(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> EntityThumbnailKindStyle {
        switch entity.entityType?.rawValue {
        case "person":
            EntityThumbnailKindStyle(label: "People", systemName: "person.2.fill", tint: .blue)
        case "location":
            EntityThumbnailKindStyle(label: "Places", systemName: "mappin.and.ellipse", tint: .green)
        case "organization":
            EntityThumbnailKindStyle(label: "Organizations", systemName: "building.2.fill", tint: .orange)
        case "event":
            EntityThumbnailKindStyle(label: "Events", systemName: "calendar", tint: .pink)
        case "concept":
            EntityThumbnailKindStyle(label: "Keywords", systemName: "tag.fill", tint: .purple)
        default:
            EntityThumbnailKindStyle(label: "Other", systemName: "questionmark.circle.fill", tint: .gray)
        }
    }

    private func entityTileSecondaryText(
        for entity: Components.Schemas.KnowledgeEntity
    ) -> String {
        let aliasCount = entity.aliases?.count ?? 0
        let corroborationCount = entity.corroborationCount ?? 0
        let aliasLabel = aliasCount == 1 ? "alias" : "aliases"
        let corroborationLabel = corroborationCount == 1 ? "corroboration" : "corroborations"
        return "\(aliasCount) \(aliasLabel) • \(corroborationCount) \(corroborationLabel)"
    }
}

// The whole-mode canvas for THIS file (Daniel, 2026-08-09: every view-mode
// file previews in place). One shared fixture environment — LibraryModeFixtures.
#Preview("Icon mode") { LibraryPreviewFixtures.mode(.icon, .icons) }
