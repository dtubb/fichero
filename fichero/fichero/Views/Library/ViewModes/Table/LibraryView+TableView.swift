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

    /// One outline row and its disclosed children.
    ///
    /// Extracted so the sectioned and unsectioned branches share it rather than
    /// carrying two copies of a three-deep nested builder. Duplicating that
    /// expression is also how `LibraryWindow.body` earned its type-check
    /// timeout — the type this returns grows with the nesting, and the checker
    /// pays for it twice if it appears twice.
    @TableRowBuilder<LibraryOutlineNode>
    private func outlineRows(for node: LibraryOutlineNode) -> some TableRowContent<LibraryOutlineNode> {
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
            let lhsIndex = order.firstIndex(of: documentId(forNodeId: lhs)) ?? Int.max
            let rhsIndex = order.firstIndex(of: documentId(forNodeId: rhs)) ?? Int.max
            if lhsIndex != rhsIndex { return lhsIndex < rhsIndex }
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
    /// Internal (not private): `selectAll()` spans the visible outline rows
    /// in table mode (#4198).
    var outlineNodes: [LibraryOutlineNode] {
        guard let outlineModel else {
            return filteredDocuments.map { LibraryOutlineNode.document($0, children: nil) }
        }
        return outlineModel.nodes(for: filteredDocuments)
    }

    /// The table's rows **in the order they are on screen**, ids only, with the
    /// disclosed children of expanded rows interleaved where the user sees them
    /// (#4377).
    ///
    /// Every other surface's ordered list is `filteredDocuments` because every
    /// other surface renders exactly those rows. The Table does not: it is an
    /// OUTLINE, so its visible list also depends on `outlineExpanded`, and when
    /// `showsUndatedSection` is on it renders dated rows then undated ones,
    /// which is not `filteredDocuments` order either. The selection set holds
    /// child node ids (`"<doc>:artifact:<id>"`) that are not in
    /// `filteredDocuments` **at all**.
    ///
    /// Handing `filteredDocuments.map(\.id)` to the shared grammar therefore
    /// looked right and was right only while everything was collapsed — which
    /// is why this survived a fix explicitly about unifying selection. Expand
    /// one row and select a child, and the id the grammar is asked about is
    /// absent from the list it is asked to find it in. Concretely: ↓ from a
    /// selected child row resolved to no index at all, hit the "nothing is
    /// selected yet" branch, and jumped the user to the FIRST row of the
    /// library.
    ///
    /// Compact width matches `outlineTableCompact`, which has no disclosure
    /// affordance and renders `filteredDocuments` flat — a stale
    /// `outlineExpanded` carried over from a regular-width window must not
    /// invent rows that iPhone is not showing.
    ///
    /// The flatten itself is `LibraryOutlineNode.visibleIds`, which ALREADY
    /// EXISTED — ⌘A has used it since #4198. That is the sharp edge of this
    /// bug: three selection paths in one mode, and the one that had the right
    /// list was not the one the arrows used. The inventory scored ⌘A "✅
    /// (outline ids)" and arrows "✅ shared" and called both correct, because
    /// it checked whether a path was shared and not WHICH LIST it shared.
    /// Routing every path through this one property is the actual fix; adding
    /// a second flatten would have been the bug again with better manners.
    var visibleOutlineRowIds: [String] {
        if horizontalSizeClass == .compact {
            return filteredDocuments.map(\.id)
        }
        // Sectioned rendering puts every dated row above every undated one, so
        // that — not `outlineNodes` order — is what "topmost" and "furthest"
        // mean on screen when the No-date section is showing (#3322).
        let roots = showsUndatedSection
            ? datedOutlineNodes + undatedOutlineNodes
            : outlineNodes
        return LibraryOutlineNode.visibleIds(of: roots, expanded: outlineExpanded)
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
            // #3322: when sorting by document date, the undated rows get their
            // own section rather than being interleaved among dated ones by the
            // engine's created_at fallback. `showsUndatedSection` is shared with
            // list mode so the two cannot disagree about when it appears.
            //
            // The dated half deliberately has NO heading: labelling it would
            // caption the ordinary case, and the only thing worth naming here
            // is the absence.
            if showsUndatedSection {
                Section {
                    ForEach(datedOutlineNodes) { node in
                        outlineRows(for: node)
                    }
                }
                Section(LibraryDateSectioning.undatedSectionTitle) {
                    ForEach(undatedOutlineNodes) { node in
                        outlineRows(for: node)
                    }
                }
            } else {
                ForEach(outlineNodes) { node in
                    outlineRows(for: node)
                }
            }
        }
        .onChange(of: selection) { oldSelection, newSelection in
            // The native Table owns its own clicks — DELIBERATELY, because
            // `NSTableView` already implements the same Finder rules and taking
            // them back would cost column drag-reorder, the native keyboard
            // loop and its accessibility. What it does not own is our anchor
            // and cursor, which the SHARED arrow-key path reads (#4160).
            //
            // Reconciling those from `newSelection` alone — what this did — can
            // never express the grammar's first rule: a ⌘-click that DESELECTED
            // a row must still move the anchor there, and that row is by
            // definition absent from `newSelection`. It survives only in the
            // difference between old and new, which `onChange` hands us and
            // this code was throwing away. The old code also returned early
            // when the selection emptied, leaving both fields pointing at rows
            // that were no longer selected (#4436).
            // ...over the rows actually ON SCREEN, not over `filteredDocuments`
            // (#4377). `reconcile` resolves "topmost" and "furthest from the
            // anchor" by indexing into this list, so with the document list it
            // scored every disclosed child row as absent and fell through to
            // the lexical-minimum fallback — deterministic, but not the visual
            // order it is supposed to be reasoning about.
            // ...and with the MODIFIERS that were down when the Table changed
            // the selection (#4531): a one-row ⇧-shrink and a one-row
            // ⌘-deselect are the same set delta, and only the gesture says
            // whether the anchor holds (range, rule 2) or follows (click,
            // rule 1). `NSEvent.modifierFlags` is still the live state inside
            // this onChange, the same seam `handleTap` reads.
            let reconciled = SelectionGrammar.reconcile(
                from: oldSelection,
                to: newSelection,
                anchor: selectionAnchor,
                in: visibleOutlineRowIds,
                modifiers: currentSelectionModifiers
            )
            selectionAnchor = reconciled.anchor
            selectionCursor = reconciled.cursor
            guard let nodeId = primaryNodeId(in: newSelection) else { return }
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
            } else if let doc = filteredDocuments.first(where: { $0.id == nodeId }) {
                // The MISSING else (night review, divergence 1): a plain
                // DOCUMENT row — the overwhelmingly common click — fell off
                // this chain, so table mode alone never drove the preview
                // directly and relied on ContentView's browserSelection
                // onChange arriving later (the double-fire path the same
                // review removed). Same direct write the other three modes
                // make in handleTap.
                detailDocument = doc
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
    /// The getter only ever emits comparators for key paths a sortable COLUMN
    /// declares (`outlineColumnComparator`); a sort field with no table column
    /// (updatedAt / fileType, toolbar-menu only) yields an empty order rather
    /// than a comparator the AppKit sort-descriptor bridge can't resolve to a
    /// column — the #4282 crash class. Rows stay correctly ordered either way:
    /// `recomputeFiltered()` sorts `filteredDocuments` upstream.
    /// The setter is total: an unrecognised key path is a full no-op, never a
    /// direction flip without a field.
    internal var outlineSortOrder: Binding<[KeyPathComparator<LibraryOutlineNode>]> {
        Binding(
            get: {
                guard let comparator = sortField.outlineColumnComparator(ascending: sortAscending) else {
                    return []
                }
                return [comparator]
            },
            set: { newOrder in
                guard let first = newOrder.first,
                      let field = LibrarySortField.field(forOutlineKeyPath: first.keyPath) else { return }
                // O2 (2026-08-09): own the sync ONCE — the two field writes
                // used to fire both field handlers, each running the server
                // sync and the refilter (2x per header click).
                isApplyingSortChange = true
                sortFieldRaw = field.rawValue
                sortAscending = first.order == .forward
                isApplyingSortChange = false
                syncSortOrder()
                saveSortSettings(for: folderId)
                syncServerListingSort()
                recomputeFiltered()
            }
        )
    }

}

// The whole-mode canvas for THIS file (Daniel, 2026-08-09: every view-mode
// file previews in place). One shared fixture environment — LibraryModeFixtures.
#Preview("Table mode") { LibraryPreviewFixtures.mode(.table, .table) }
