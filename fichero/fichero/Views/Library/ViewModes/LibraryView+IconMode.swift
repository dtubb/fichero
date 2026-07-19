import FicheroAPIClient
import SwiftUI

// MARK: - Icons View (Grid)

extension LibraryView {
    var iconsView: some View {
        let itemMin = CGFloat(max(60, 120 * iconViewScale))
        let itemMax = CGFloat(max(80, 150 * iconViewScale))
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
                            }
                        } else {
                            ForEach(filteredDocuments) { doc in
                                DocumentThumbnailView(
                                    document: doc,
                                    isSelected: selection.contains(doc.id),
                                    selectedTint: selectionTint,
                                    scale: CGFloat(iconViewScale)
                                )
                                .id(doc.id)
                                .draggable(libraryItemDrag(for: doc))
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
                // In icon mode, ScrollView may consume arrow keys for scrolling first.
                // Handle them at this level so keyboard selection always works.
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
                    if let id = selection.first {
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
                // above what's rendered. (#929)
                .onChange(of: selection.first) { _, id in
                    guard let id else { return }
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

    private func scheduleThumbnailPrefetch(around documentId: String) {
        guard !isShowingEntitiesCollection,
              let index = documentIndexById[documentId] else { return }

        let behind = max(gridColumnCount * 2, 8)
        let ahead = max(gridColumnCount * 8, 24)
        let start = max(0, index - behind)
        let end = min(filteredDocuments.count, index + ahead)
        let imageIds = filteredDocuments[start..<end]
            .filter { $0.fileType == .image && $0.docType != .folder && !prefetchedThumbnailIds.contains($0.id) }
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
