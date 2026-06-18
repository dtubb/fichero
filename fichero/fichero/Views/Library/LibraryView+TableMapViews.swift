import SwiftUI

// MARK: - Table + Map Display Modes

extension LibraryView {

    // MARK: - Table View (Sortable columns + Mac-native column customization)

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
            // Child-group rows carry "<docId>:<type>" ids — drop the
            // suffix so a context-menu on a child still targets its doc.
            if let firstId = items.first,
               let doc = filteredDocuments.first(where: { $0.id == documentId(forNodeId: firstId) }) {
                documentContextMenu(for: doc)
            }
        }
        .onTapGesture(count: 2) {
            if let firstId = selection.first,
               let doc = filteredDocuments.first(where: { $0.id == documentId(forNodeId: firstId) }) {
                handleDoubleClick(doc)
            }
        }
    }

    /// Strip a child-group node's `:type` suffix back to the document id.
    private func documentId(forNodeId nodeId: String) -> String {
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
        // same starting layout. Daniel: 'we want this in the mac way
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
                DisclosureTableRow(node, isExpanded: expansionBinding(for: node)) {
                    ForEach(node.children ?? []) { child in
                        TableRow(child)
                    }
                }
            }
        }
    }

    /// Node-typed sort-order binding mapped onto the existing
    /// document-level sort persistence (#2258). The outline columns sort
    /// `LibraryOutlineNode`s, but the per-folder sort state and
    /// `filteredDocuments` ordering stay `Document`-keyed — this binding
    /// translates header clicks into `sortFieldRaw`/`sortAscending`
    /// without forking the persistence machinery.
    private var outlineSortOrder: Binding<[KeyPathComparator<LibraryOutlineNode>]> {
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

    // MARK: Compact width (iPhone) — plain document list, no disclosure

    @ViewBuilder
    private var outlineTableCompact: some View {
        Table(
            of: LibraryOutlineNode.self,
            selection: $selection,
            sortOrder: outlineSortOrder,
            columnCustomization: $tableColumnCustomization
        ) {
            outlineColumns
        } rows: {
            ForEach(filteredDocuments) { doc in
                TableRow(LibraryOutlineNode.document(doc, children: nil))
            }
        }
    }

    /// Expansion binding for a document row. Flipping it open kicks the
    /// document's rollup fetch so its child-group rows materialise.
    private func expansionBinding(for node: LibraryOutlineNode) -> Binding<Bool> {
        Binding(
            get: { outlineExpanded.contains(node.id) },
            set: { isOpen in
                if isOpen {
                    outlineExpanded.insert(node.id)
                    let docId = node.document.id
                    Task { await outlineModel?.loadRollup(for: docId) }
                } else {
                    outlineExpanded.remove(node.id)
                }
            }
        )
    }

    /// Shared columns for both the regular (outline) and compact (flat)
    /// tables. Columns close over `LibraryOutlineNode`: a `.document`
    /// node renders the familiar per-document cells; a `.childGroup` node
    /// renders only in the Name column (its summary label), staying blank
    /// elsewhere so child rows read as a clean indented sub-list.
    @TableColumnBuilder<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>>
    private var outlineColumns: some TableColumnContent<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>> {
        TableColumn("Name", value: \.document.name) { node in
            outlineNameCell(for: node)
        }
        .width(min: 150, ideal: 200)
        .customizationID("name")
        .disabledCustomizationBehavior(.visibility)  // Always visible

        TableColumn("Status", value: \.document.status.rawValue) { node in
            documentColumnCell(for: node, columnId: "status")
        }
        .width(min: 80, ideal: 100)
        .customizationID("status")

        TableColumn("Output") { node in
            documentColumnCell(for: node, columnId: "output")
        }
        .width(min: 150, ideal: 250)
        .customizationID("output")

        TableColumn("Created", value: \.document.createdAt) { node in
            documentColumnCell(for: node, columnId: "createdDate")
        }
        .width(min: 80, ideal: 100)
        .customizationID("createdDate")

        // Per-entity-type columns (#519). Each renders FlowLayout
        // lozenges via ArtifactEntityCell for that doc's artifacts
        // of one type. All hidden by default; users opt in via the
        // column-header right-click menu (Mac native).
        //
        // SwiftUI's TableColumnBuilder caps at 10 children — we
        // dropped path/modifiedDate/size/artifacts(combined) to fit.
        TableColumn("People") { node in
            documentColumnCell(for: node, columnId: "people")
        }
        .width(min: 120, ideal: 200)
        .customizationID("people")
        .defaultVisibility(.hidden)

        TableColumn("Places") { node in
            documentColumnCell(for: node, columnId: "places")
        }
        .width(min: 120, ideal: 180)
        .customizationID("places")
        .defaultVisibility(.hidden)

        TableColumn("Organizations") { node in
            documentColumnCell(for: node, columnId: "organizations")
        }
        .width(min: 120, ideal: 180)
        .customizationID("organizations")
        .defaultVisibility(.hidden)

        TableColumn("Dates") { node in
            documentColumnCell(for: node, columnId: "dates")
        }
        .width(min: 100, ideal: 140)
        .customizationID("dates")
        .defaultVisibility(.hidden)

        TableColumn("Events") { node in
            documentColumnCell(for: node, columnId: "events")
        }
        .width(min: 120, ideal: 200)
        .customizationID("events")
        .defaultVisibility(.hidden)

        TableColumn("Keywords") { node in
            documentColumnCell(for: node, columnId: "keywords")
        }
        .width(min: 120, ideal: 200)
        .customizationID("keywords")
        .defaultVisibility(.hidden)
    }

    /// Name-column cell. Documents render the existing name cell; a
    /// child-group renders its type icon + count summary ("12 entities").
    @ViewBuilder
    private func outlineNameCell(for node: LibraryOutlineNode) -> some View {
        switch node.kind {
        case .document:
            tableCellView(for: "name", document: node.document)
        case .childGroup(let type):
            Label(type.groupLabel(count: node.count), systemImage: type.systemImage)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    /// Non-name columns render the document cell for document rows and
    /// stay empty for child-group rows.
    @ViewBuilder
    private func documentColumnCell(for node: LibraryOutlineNode, columnId: String) -> some View {
        switch node.kind {
        case .document:
            tableCellView(for: columnId, document: node.document)
        case .childGroup:
            EmptyView()
        }
    }

    // MARK: - Map View (Tinderbox-style canvas)

    var mapView: some View {
        ScrollView([.horizontal, .vertical]) {
            ZStack(alignment: .topLeading) {
                // Grid background (fills the scaled canvas frame)
                MapGridBackground()

                // Document cards at scaled positions
                ForEach(filteredDocuments) { doc in
                    let base = mapPositions[doc.id] ?? defaultMapPosition(for: doc)
                    let pos = CGPoint(
                        x: base.x * CGFloat(mapCanvasScale),
                        y: base.y * CGFloat(mapCanvasScale)
                    )
                    MapCard(
                        document: doc,
                        isSelected: selection.contains(doc.id),
                        position: pos
                    )
                    .onTapGesture(count: 2) {
                        handleDoubleClick(doc)
                    }
                    .onTapGesture {
                        handleTap(doc)
                    }
                    .gesture(
                        DragGesture()
                            .onChanged { value in
                                // Store in unscaled document coordinates
                                mapPositions[doc.id] = CGPoint(
                                    x: value.location.x / CGFloat(mapCanvasScale),
                                    y: value.location.y / CGFloat(mapCanvasScale)
                                )
                            }
                    )
                    .contextMenu {
                        documentContextMenu(for: doc)
                    }
                }
            }
            .frame(
                width: mapCanvasWidth * CGFloat(mapCanvasScale),
                height: mapCanvasHeight * CGFloat(mapCanvasScale)
            )
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            initializeMapPositions()
        }
    }

    // MARK: - Map Helpers

    func initializeMapPositions() {
        // Only initialize if not already set
        for (index, doc) in filteredDocuments.enumerated() where mapPositions[doc.id] == nil {
            let row = index / 4
            let col = index % 4
            mapPositions[doc.id] = CGPoint(
                x: 100 + CGFloat(col) * 200,
                y: 100 + CGFloat(row) * 150
            )
        }
    }

    func defaultMapPosition(for doc: Document) -> CGPoint {
        guard let index = filteredDocuments.firstIndex(where: { $0.id == doc.id }) else {
            return CGPoint(x: 100, y: 100)
        }
        let row = index / 4
        let col = index % 4
        return CGPoint(x: 100 + CGFloat(col) * 200, y: 100 + CGFloat(row) * 150)
    }

    private var mapCanvasWidth: CGFloat {
        let maxX = mapPositions.values.map(\.x).max() ?? 0
        let cols = min(3, max(0, filteredDocuments.count - 1))
        let countWidth = 100 + CGFloat(cols) * 200 + 200
        return max(1200, max(maxX + 200, countWidth))
    }

    private var mapCanvasHeight: CGFloat {
        let maxY = mapPositions.values.map(\.y).max() ?? 0
        let rows = filteredDocuments.isEmpty ? 0 : (filteredDocuments.count - 1) / 4
        let countHeight = 100 + CGFloat(rows) * 150 + 200
        return max(800, max(maxY + 200, countHeight))
    }
}
