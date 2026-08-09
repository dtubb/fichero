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

    var iconsView: some View {
        let (itemMin, itemMax) = Self.iconGridItemBounds(scale: iconViewScale)
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
                                    scale: CGFloat(iconViewScale)
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
                                        scale: iconViewScale,
                                        isRenaming: renamingDocumentId == doc.id
                                    ),
                                    isSelected: selection.contains(doc.id),
                                    tint: selectionTint
                                ) {
                                    DocumentThumbnailView(
                                        document: doc,
                                        isSelected: selection.contains(doc.id),
                                        selectedTint: selectionTint,
                                        scale: CGFloat(iconViewScale),
                                        isRenaming: renamingDocumentId == doc.id,
                                        editingName: $editingName,
                                        onCommitRename: commitRename,
                                        onCancelRename: cancelRename
                                    )
                                }
                                .equatable()
                                .id(doc.id)
                                .iconTileFrame(id: doc.id, in: "libraryIconGrid")
                                .draggable(libraryItemDrag(for: doc)) {
                                    DragPreviewLabel(name: doc.name, systemImage: doc.fileType?.icon ?? doc.docType.icon)
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
                                .contextMenu {
                                    documentContextMenu(for: doc)
                                }
                                .onAppear {
                                    scheduleThumbnailPrefetch(around: doc.id)
                                }
                            }
                        }
                    }
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                }
                .coordinateSpace(name: "libraryIconGrid")
                .onPreferenceChange(IconTileFramesKey.self) { iconTileFrames = $0 }
                // Click in the gutter/empty space deselects, like Finder
                // (#4160). Tile taps win — their gestures are deeper.
                .onTapGesture {
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
                            let rect = LibraryMarquee.rect(from: value.startLocation, to: value.location)
                            // Per-tick: mutate the box (overlay-only render).
                            marqueeModel.rect = rect
                            if marqueeModel.baseSelection == nil {
                                marqueeModel.baseSelection = selection
                            }
                            // Selection applies ONLY when the hit set changes
                            // — the expensive grid re-render happens when a
                            // tile enters/leaves the band, not per pixel.
                            let hits = LibraryMarquee.hitIds(in: iconTileFrames, rect: rect)
                            guard hits != marqueeModel.lastHits else { return }
                            marqueeModel.lastHits = hits
                            apply(SelectionGrammar.marquee(
                                ids: hits,
                                selection: marqueeModel.baseSelection ?? selection,
                                modifiers: currentSelectionModifiers
                            ))
                        }
                        .onEnded { _ in
                            marqueeModel.rect = nil
                            marqueeModel.baseSelection = nil
                            marqueeModel.lastHits = []
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
                            let stepped = (clamped * 20).rounded() / 20
                            if stepped != iconViewScale {
                                iconViewScale = stepped
                            }
                        }
                        .onEnded { _ in
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

    private func resetThumbnailPrefetch() {
        prefetchedThumbnailIds.removeAll()
        thumbnailPrefetchTask?.cancel()
        thumbnailPrefetchTask = nil
    }

    // Internal (not private): the list view prefetches with the same window
    // from ITS rows' onAppear (#4160) — list rows previously fetched one at a
    // time on scroll, so every scroll showed skeleton churn. The table's name
    // cell joins them now that it renders thumbnails too (#4202).
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
