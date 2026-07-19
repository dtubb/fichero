import SwiftUI

// MARK: - List View (Mail-style compact rows)
// Uses ScrollView+LazyVStack instead of List to avoid AppKit NSTableView
// intercepting arrow key events before our .onKeyPress handlers fire.

extension LibraryView {
    var listView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    if isShowingEntitiesCollection {
                        ForEach(filteredEntities, id: \.stableInspectorId) { entity in
                            let entityId = entitySelectionId(for: entity)
                            LibrarySelectableRow(
                                identity: entity,
                                isSelected: selection.contains(entityId),
                                tint: selectionFill
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

                            Divider()
                                .padding(.leading, 12)
                        }
                    } else {
                        ForEach(filteredDocuments) { doc in
                            LibrarySelectableRow(
                                // Identity must capture EVERYTHING the row content
                                // renders from — the document AND which entity-type
                                // tags are shown — so a filter change still re-renders
                                // the row (isSelected/tint cover selection + focus).
                                identity: DocRowIdentity(document: doc, visibleEntityTypes: listVisibleEntityTypes),
                                isSelected: selection.contains(doc.id),
                                tint: selectionFill
                            ) {
                                MailStyleRow(
                                    document: doc,
                                    isSelected: selection.contains(doc.id),
                                    visibleEntityTypes: listVisibleEntityTypes
                                ) { tag in
                                    searchText = tag
                                    showFilterBar = true
                                }
                            }
                            .equatable()
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

                            Divider()
                                .padding(.leading, 12)
                        }
                    }
                }
            }
            .onChange(of: listScrollTarget) { _, id in
                guard let id else { return }
                proxy.scrollTo(id, anchor: nil)
                listScrollTarget = nil
            }
            // PDF preview scrolling → selection updates → list scrolls to
            // keep the selected row visible. Mirrors the iconView watcher
            // for the same reason: PDF-driven selection wasn't reaching
            // the ScrollViewReader without it. (#929)
            .onChange(of: selection.first) { _, id in
                guard let id else { return }
                withAnimation(.easeInOut(duration: 0.15)) {
                    proxy.scrollTo(id, anchor: nil)
                }
            }
            .onAppear {
                // Restored-from-launch selection scroll for list view (#808).
                if let id = selection.first {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            proxy.scrollTo(id, anchor: .center)
                        }
                    }
                }
            }
            .padding(.leading, browserLeadingInset)
        }
    }
}
