import FicheroAPIClient
import SwiftUI

// MARK: - Table View (Sortable columns + Mac-native column customization)

extension LibraryView {

    /// The library Table is an expandable OUTLINE (#2258): each document
    /// row discloses its typed children (pages / artifacts / entities /
    /// notes / claims), assembled into `LibraryOutlineNode`s. Collapsed
    /// rows show cheap per-type rollup counts; the children stream in
    /// when a row is expanded. On iPhone (compact width) the table has no
    /// disclosure affordance, so it collapses to a plain document list.
    var tableView: some View {
        Group {
            if horizontalSizeClass == .compact {
                outlineTableCompact
            } else {
                outlineTableRegular
            }
        }
        .tableStyle(.inset)
        #if os(macOS)
        .alternatingRowBackgrounds()
        #endif
        .contextMenu(forSelectionType: String.self) { items in
            // Deterministic primary pick, not Set hash order (#4160):
            // right-clicking a multi-selection targeted an arbitrary doc.
            // Child-group rows carry "<docId>:<type>" ids — drop the
            // suffix so a context-menu on a child still targets its doc.
            if let firstId = primaryNodeId(in: items),
               let doc = filteredDocuments.first(where: { $0.id == documentId(forNodeId: firstId) }) {
                documentContextMenu(for: doc)
            }
        }
        .onTapGesture(count: 2) {
            handleOutlineDoubleClickSelection()
        }
        .padding(.leading, browserLeadingInset)
    }

    private func handleOutlineDoubleClickSelection() {
        // Act on the deterministic primary ROW id, not the document-level
        // cursor: child ids ("<doc>:artifact:<id>") aren't in
        // filteredDocuments, so the step-2 cursor swap silently killed the
        // artifact-detail-window path for child rows (#4160 step 3).
        guard let firstId = primaryNodeId(in: selection) else { return }
        if let artifactSelection = artifactSelectionForNodeId(firstId) {
            openArtifactDetailWindow(for: artifactSelection)
            return
        }
        if let doc = filteredDocuments.first(where: { $0.id == documentId(forNodeId: firstId) }) {
            handleDoubleClick(doc)
        }
    }

    /// Deterministic primary node id for a set of outline-row ids: the
    /// shared keyboard cursor when it's in the set, else the id whose
    /// PARENT DOCUMENT comes first in visual order (ties broken lexically —
    /// never Set hash order).
    func primaryNodeId(in items: Set<String>) -> String? {
        if items.count <= 1 { return items.min() }
        if let cursor = selectionCursor, items.contains(cursor) { return cursor }
        let order = filteredDocuments.map(\.id)
        return items.min { lhs, rhs in
            let li = order.firstIndex(of: documentId(forNodeId: lhs)) ?? Int.max
            let ri = order.firstIndex(of: documentId(forNodeId: rhs)) ?? Int.max
            if li != ri { return li < ri }
            return lhs < rhs
        }
    }

    private func openArtifactDetailWindow(for selection: (document: Document, artifact: Artifact)) {
        FocusedArtifact.shared.select(
            selection.artifact.id,
            documentId: selection.document.id,
            documentName: selection.document.name,
            in: [selection.artifact]
        )
        openWindow(id: "artifact-detail")
    }

    /// Strip a child-group node's `:type` suffix back to the document id.
    func documentId(forNodeId nodeId: String) -> String {
        if let colon = nodeId.firstIndex(of: ":") {
            return String(nodeId[..<colon])
        }
        return nodeId
    }

    /// Top-level outline nodes for the currently filtered documents, with
    /// any already-loaded child groups attached. Built fresh each render
    /// from the (value-type) model cache so newly-loaded rollups appear.
    private var outlineNodes: [LibraryOutlineNode] {
        guard let outlineModel else {
            return filteredDocuments.map { LibraryOutlineNode.document($0, children: nil) }
        }
        return outlineModel.nodes(for: filteredDocuments)
    }

    // MARK: Regular width — expandable DisclosureTableRow outline

    @ViewBuilder
    private var outlineTableRegular: some View {
        // Native column customization: right-click on any column header
        // surfaces SwiftUI's built-in show/hide + reorder menu. Each
        // column needs a stable .customizationID; default visibility
        // matches the prior @SceneStorage defaults so users see the
        // same starting layout. The maintainer: 'we want this in the mac way
        // which is a contextual menu in the table view header.' (#519)
        Table(
            of: LibraryOutlineNode.self,
            selection: $selection,
            sortOrder: outlineSortOrder,
            columnCustomization: $tableColumnCustomization
        ) {
            outlineColumns
        } rows: {
            ForEach(outlineNodes) { node in
                if nodeCanExpand(node) {
                    DisclosureTableRow(node, isExpanded: expansionBinding(for: node)) {
                        ForEach(node.children ?? []) { childGroup in
                            if nodeCanExpand(childGroup) {
                                DisclosureTableRow(childGroup, isExpanded: expansionBinding(for: childGroup)) {
                                    ForEach(childGroup.children ?? []) { child in
                                        TableRow(child)
                                    }
                                }
                            } else {
                                TableRow(childGroup)
                            }
                        }
                    }
                } else {
                    TableRow(node)
                }
            }
        }
        .onChange(of: selection) { _, newSelection in
            guard let nodeId = primaryNodeId(in: newSelection) else { return }
            // Keep the shared keyboard cursor live in table mode (#4160):
            // the native Table writes `selection` directly, so the
            // handleTap/applySelection paths that normally maintain
            // cursor+anchor never run here — without this, Return/Space/
            // follow-scroll pointed at the topmost row, not the clicked one.
            selectionCursor = nodeId
            if selectionAnchor.map({ !newSelection.contains($0) }) ?? true {
                selectionAnchor = nodeId
            }
            if let pageDoc = pageDocumentForNodeId(nodeId) {
                onPageFocus(pageDoc)
            } else if let artifactSelection = artifactSelectionForNodeId(nodeId) {
                detailDocument = artifactSelection.document
                FocusedArtifact.shared.select(
                    artifactSelection.artifact.id,
                    documentId: artifactSelection.document.id,
                    documentName: artifactSelection.document.name,
                    in: [artifactSelection.artifact]
                )
            } else if let entitySelection = entitySelectionForNodeId(nodeId) {
                detailDocument = entitySelection.document
                if let entityId = entitySelection.entity.id {
                    kgFocusState.focusEntity(entityId: entityId)
                }
            } else if let claimSelection = claimSelectionForNodeId(nodeId) {
                detailDocument = claimSelection.document
                if let claimId = claimSelection.claim.id {
                    kgFocusState.focusClaim(
                        claimId: claimId,
                        entityId: claimSelection.claim.entityIds?.first,
                        sourceDocumentId: claimSelection.claim.sourceDocumentId
                    )
                }
            }
        }
    }

    /// Search the current outline nodes recursively for a `.pageItem` matching
    /// the given node id. Used to fire `onPageFocus` on page-row selection.
    private func pageDocumentForNodeId(_ nodeId: String) -> Document? {
        if let node = findNode(withId: nodeId, in: outlineNodes),
           case .pageItem(let page) = node.kind {
            return page
        }
        return nil
    }

    private func artifactSelectionForNodeId(_ nodeId: String) -> (document: Document, artifact: Artifact)? {
        if let node = findNode(withId: nodeId, in: outlineNodes),
           case .artifactItem(let artifact) = node.kind {
            return (node.document, artifact)
        }
        return nil
    }

    private func entitySelectionForNodeId(_ nodeId: String) -> (document: Document, entity: Components.Schemas.KnowledgeEntity)? {
        if let node = findNode(withId: nodeId, in: outlineNodes),
           case .entityItem(let entity) = node.kind {
            return (node.document, entity)
        }
        return nil
    }

    private func claimSelectionForNodeId(_ nodeId: String) -> (document: Document, claim: Components.Schemas.KnowledgeClaim)? {
        if let node = findNode(withId: nodeId, in: outlineNodes),
           case .claimItem(let claim) = node.kind {
            return (node.document, claim)
        }
        return nil
    }

    private func findNode(withId nodeId: String, in nodes: [LibraryOutlineNode]) -> LibraryOutlineNode? {
        for node in nodes {
            if node.id == nodeId {
                return node
            }
            if let children = node.children,
               let found = findNode(withId: nodeId, in: children) {
                return found
            }
        }
        return nil
    }

    private func nodeCanExpand(_ node: LibraryOutlineNode) -> Bool {
        node.canExpand
    }

    /// Node-typed sort-order binding mapped onto the existing
    /// document-level sort persistence (#2258). The outline columns sort
    /// `LibraryOutlineNode`s, but the per-folder sort state and
    /// `filteredDocuments` ordering stay `Document`-keyed — this binding
    /// translates header clicks into `sortFieldRaw`/`sortAscending`
    /// without forking the persistence machinery.
    internal var outlineSortOrder: Binding<[KeyPathComparator<LibraryOutlineNode>]> {
        Binding(
            get: {
                let ascending = sortAscending
                let order: SortOrder = ascending ? .forward : .reverse
                switch sortField {
                case .name:
                    return [.init(\.document.name, order: order)]
                case .createdAt:
                    return [.init(\.document.createdAt, order: order)]
                case .updatedAt:
                    return [.init(\.document.updatedAt, order: order)]
                case .fileType:
                    return [.init(\.document.sortableFileType, order: order)]
                case .status:
                    return [.init(\.document.status.rawValue, order: order)]
                }
            },
            set: { newOrder in
                guard let first = newOrder.first else { return }
                let ascending = first.order == .forward
                if first.keyPath == \LibraryOutlineNode.document.name {
                    sortFieldRaw = LibrarySortField.name.rawValue
                } else if first.keyPath == \LibraryOutlineNode.document.createdAt {
                    sortFieldRaw = LibrarySortField.createdAt.rawValue
                } else if first.keyPath == \LibraryOutlineNode.document.updatedAt {
                    sortFieldRaw = LibrarySortField.updatedAt.rawValue
                } else if first.keyPath == \LibraryOutlineNode.document.sortableFileType {
                    sortFieldRaw = LibrarySortField.fileType.rawValue
                } else if first.keyPath == \LibraryOutlineNode.document.status.rawValue {
                    sortFieldRaw = LibrarySortField.status.rawValue
                }
                sortAscending = ascending
                saveSortSettings(for: folderId)
            }
        )
    }

}
