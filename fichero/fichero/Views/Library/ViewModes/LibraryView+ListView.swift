import FicheroAPIClient
import SwiftUI

// MARK: - List View (Mail-style compact rows)
// macOS uses ScrollView+LazyVStack instead of List to avoid AppKit NSTableView
// intercepting arrow key events before our .onKeyPress handlers fire.
// iOS/iPadOS use a native List (#2501): touch rows get the platform-standard
// `.swipeActions` (swipe-to-delete), which SwiftUI only provides inside List —
// and the AppKit key-interception rationale does not apply on touch platforms.
// Both branches share the SAME row builders, tap handlers, context menu, and
// delete pipeline (promptDelete → confirm dialog → document.delete action).

extension LibraryView {
    var listView: some View {
        ScrollViewReader { proxy in
            #if os(macOS)
            macList(proxy: proxy)
            #else
            touchList(proxy: proxy)
            #endif
        }
    }

    // MARK: - Shared rows

    /// One document row with every shared behavior attached (selection wash,
    /// tap/double-tap, drag, folder drop, context menu, thumbnail prefetch).
    /// Container-specific chrome (macOS Divider, iOS swipe actions and list-row
    /// styling) stays with the caller.
    @ViewBuilder
    private func documentRow(_ doc: Document) -> some View {
        LibrarySelectableRow(
            // Identity must capture EVERYTHING the row content
            // renders from — the document AND which entity-type
            // tags are shown — so a filter change still re-renders
            // the row (isSelected/tint cover selection + focus).
            identity: DocRowIdentity(
                document: doc,
                visibleEntityTypes: listVisibleEntityTypes,
                isRenaming: renamingDocumentId == doc.id
            ),
            isSelected: selection.contains(doc.id),
            tint: selectionTint
        ) {
            MailStyleRow(
                document: doc,
                isSelected: selection.contains(doc.id),
                isPaneFocused: isPaneFocused,
                isRenaming: renamingDocumentId == doc.id,
                editingName: $editingName,
                onCommitRename: commitRename,
                onCancelRename: cancelRename,
                visibleEntityTypes: listVisibleEntityTypes
            ) { tag in
                searchText = tag
                showFilterBar = true
            }
        }
        .equatable()
        .modifier(LibraryRowHoverWash(enabled: !selection.contains(doc.id)))
        .id(doc.id)
        .draggable(libraryItemDrag(for: doc))
        // Folder rows accept in-app item drops (#4124).
        .modifier(LibraryFolderCellDrop(
            isFolder: doc.docType == .folder,
            onDropItems: { items in
                moveDraggedItems(items, into: doc)
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
        // Same look-ahead window icon mode uses (#4160):
        // batch-prefetch thumbnails around the appearing
        // row instead of one fetch per row on scroll.
        .onAppear {
            scheduleThumbnailPrefetch(around: doc.id)
        }
    }

    /// One entity row with the shared selection/tap behaviors attached.
    @ViewBuilder
    private func entityListRow(_ entity: Components.Schemas.KnowledgeEntity) -> some View {
        let entityId = entitySelectionId(for: entity)
        LibrarySelectableRow(
            identity: entity,
            isSelected: selection.contains(entityId),
            tint: selectionTint
        ) {
            EntityRow(
                entity: entity,
                claimCount: entity.corroborationCount ?? 0,
                style: .browser
            )
        }
        .equatable()
        .id(entityId)
        .onTapGesture(count: 2) {
            handleEntityDoubleClick(entity)
        }
        .onTapGesture {
            handleEntityTap(entity)
        }
    }

    /// The scroll-sync behaviors both containers share: scroll-to targets,
    /// selection-follow, and the restored-selection scroll on appear.
    private func listScrollSync(_ content: some View, proxy: ScrollViewProxy) -> some View {
        content
            .onChange(of: listScrollTarget) { _, id in
                guard let id else { return }
                proxy.scrollTo(id, anchor: nil)
                listScrollTarget = nil
            }
            // Double-click / layout-change force-centers the row, mirroring
            // icon mode — this target was previously set but never consumed
            // in list mode, leaving a stale value that fired a spurious
            // centering scroll on a later switch to icon mode (#4160).
            .onChange(of: listScrollCenterTarget) { _, id in
                guard let id else { return }
                withAnimation(.easeInOut(duration: 0.15)) {
                    proxy.scrollTo(id, anchor: .center)
                }
                listScrollCenterTarget = nil
            }
            // PDF preview scrolling → selection updates → list scrolls to
            // keep the selected row visible. Mirrors the iconView watcher
            // for the same reason: PDF-driven selection wasn't reaching
            // the ScrollViewReader without it. (#929) Scrolls to the ORDERED
            // primary row, not Set.first hash order (#4160).
            .onChange(of: selection) { _, _ in
                guard let id = orderedPrimarySelectionId else { return }
                withAnimation(.easeInOut(duration: 0.15)) {
                    proxy.scrollTo(id, anchor: nil)
                }
            }
            .onAppear {
                // Restored-from-launch selection scroll for list view (#808).
                if let id = orderedPrimarySelectionId {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            proxy.scrollTo(id, anchor: .center)
                        }
                    }
                }
            }
    }

    #if os(macOS)
    // MARK: - macOS container (ScrollView + LazyVStack, unchanged)

    private func macList(proxy: ScrollViewProxy) -> some View {
        listScrollSync(
            ScrollView {
                LazyVStack(spacing: 0) {
                    if isShowingEntitiesCollection {
                        ForEach(filteredEntities, id: \.stableInspectorId) { entity in
                            entityListRow(entity)

                            Divider()
                                .padding(.leading, 12)
                        }
                    } else {
                        ForEach(filteredDocuments) { doc in
                            documentRow(doc)

                            Divider()
                                .padding(.leading, 12)
                        }
                    }
                }
            }
            // Same rationale as icon mode (#575): .focusable() so the
            // .onKeyPress handlers on the LibraryView body actually receive
            // arrow/Return/type-select keys — ScrollView swallows them
            // otherwise. List mode was never patched when icon mode was, so
            // keyboard nav only worked when a child incidentally held focus
            // (#4160). The container focus ring is suppressed; selection is
            // the visible focus.
            .focusable()
            .focusEffectDisabled()
            // Click in the empty space below the rows deselects, like
            // Finder/NNW (#4160). Row taps win — their own tap gestures are
            // deeper in the hierarchy.
            .onTapGesture {
                selection.removeAll()
                selectionAnchor = nil
                selectionCursor = nil
            },
            proxy: proxy
        )
        .padding(.leading, browserLeadingInset)
    }
    #else
    // MARK: - iOS/iPadOS container (native List, #2501)

    private func touchList(proxy: ScrollViewProxy) -> some View {
        listScrollSync(
            List {
                if isShowingEntitiesCollection {
                    ForEach(filteredEntities, id: \.stableInspectorId) { entity in
                        entityListRow(entity)
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                        // No swipe-to-delete on entity rows: deleting a
                        // knowledge-graph entity is a KG operation with its
                        // own consequences/undo story (see promptDeleteSelected).
                    }
                } else {
                    ForEach(filteredDocuments) { doc in
                        documentRow(doc)
                            // The rows draw their own selection wash and
                            // Mail-style layout — keep List chrome out of the
                            // way so both platforms render identically.
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                            // Swipe-to-delete (#2501): the platform-standard
                            // trailing swipe, routed through the SAME audited
                            // delete pipeline as the context menu — Finder
                            // semantics (selection-aware), confirm dialog,
                            // then the document.delete action. Never a
                            // parallel delete path. Full swipe still confirms.
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    promptDelete(for: doc)
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                    }
                }
            }
            .listStyle(.plain),
            proxy: proxy
        )
    }
    #endif
}
