import FicheroAPIClient
import SwiftUI

// MARK: Compact width (iPhone) — plain document list, no disclosure

extension LibraryView {

    @ViewBuilder
    internal var outlineTableCompact: some View {
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

    /// Expansion binding for an outline row. Opening a document row kicks the
    /// document's rollup + typed-child fetches so child rows materialise.
    internal func expansionBinding(for node: LibraryOutlineNode) -> Binding<Bool> {
        Binding(
            get: { outlineExpanded.contains(node.id) },
            set: { isOpen in
                if isOpen {
                    outlineExpanded.insert(node.id)
                    let docId = node.document.id
                    if case .document = node.kind {
                        Task {
                            await outlineModel?.loadRollup(for: docId)
                            await outlineModel?.loadArtifacts(for: docId)
                            await outlineModel?.loadEntities(for: docId)
                            await outlineModel?.loadClaims(for: docId)
                        }
                    }
                } else {
                    outlineExpanded.remove(node.id)
                }
            }
        )
    }

    /// Push the current page documents (already in documentStore) into the
    /// outline model so page-item rows have data without an extra fetch (#2405).
    func syncPagesByParentId() {
        guard let model = outlineModel else { return }
        let pages = documentStore.currentDocuments.filter { $0.docType == .page }
        model.pagesByParentId = Dictionary(grouping: pages, by: { $0.parentId ?? "" })
    }

    /// Shared columns for both the regular (outline) and compact (flat)
    /// tables. Columns close over `LibraryOutlineNode`: a `.document`
    /// node renders the familiar per-document cells; a `.childGroup` node
    /// renders only in the Name column (its summary label), staying blank
    /// elsewhere so child rows read as a clean indented sub-list.
    @TableColumnBuilder<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>>
    internal var outlineColumns: some TableColumnContent<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>> {
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

    /// Name-column cell. Documents render the existing name cell; child-group rows
    /// show a count summary ("12 entities"); page/artifact items show their own label.
    @ViewBuilder
    private func outlineNameCell(for node: LibraryOutlineNode) -> some View {
        switch node.kind {
        case .document:
            tableCellView(for: "name", document: node.document)
        case .childGroup(let type):
            Label(type.groupLabel(count: node.count), systemImage: type.systemImage)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .draggable(LibraryItemDrag(
                    kind: .group,
                    id: node.id,
                    documentId: node.document.id,
                    text: type.groupLabel(count: node.count)
                ))
        case .pageItem(let page):
            Label(
                page.pageThumbnailLabel.map { "Page \($0)" } ?? page.name,
                systemImage: "doc.richtext"
            )
            .font(.subheadline)
            .foregroundStyle(.primary)
            .draggable(libraryItemDrag(for: page))
        case .artifactItem(let artifact):
            Label(
                artifact.stepName ?? artifact.artifactType,
                systemImage: "shippingbox"
            )
            .font(.subheadline)
            .foregroundStyle(.primary)
            .draggable(LibraryItemDrag(
                kind: .artifact,
                id: artifact.id,
                documentId: artifact.documentId,
                text: artifact.content?.isEmpty == false
                    ? artifact.content ?? artifact.artifactTypeDisplayName
                    : artifact.artifactTypeDisplayName
            ))
        case .entityItem(let entity):
            Label(entity.canonicalName, systemImage: "person.crop.circle")
                .font(.subheadline)
                .foregroundStyle(.primary)
        case .claimItem(let claim):
            Label(claim.displayMergeName, systemImage: "quote.bubble")
                .font(.subheadline)
                .foregroundStyle(.primary)
        }
    }

    /// Non-name columns render the document cell for document rows and
    /// stay empty for child-group and item rows.
    @ViewBuilder
    private func documentColumnCell(for node: LibraryOutlineNode, columnId: String) -> some View {
        switch node.kind {
        case .document:
            tableCellView(for: columnId, document: node.document)
        case .childGroup, .pageItem, .artifactItem, .entityItem, .claimItem:
            EmptyView()
        }
    }

}

// Canvas (2D) is now rendered by `Spatial2DCanvas` off the shared
// canvasLayoutStore (#2667). The old `mapView` + its ephemeral, in-memory
// `mapPositions` grid (never persisted, reset every launch) were the
// duplicate this merge retires. `MapCard`/`MapGridBackground` in
// LibraryMapComponents.swift are now unreferenced; manager can `git rm`
// that file (pbxproj edits are gated to scripts, not hand-edited here).
