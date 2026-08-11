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
            // Same per-cell boundary injection as documentColumnCell — the
            // name cell hosts the activity indicator (DocumentStore) and the
            // thumbnail well (StorageService).
            outlineNameCell(for: node)
                .modifier(tableCellServiceInjection)
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

        // #3322: the date the document was WRITTEN, beside Created — which is
        // IMPORT time and, for a 19th-century diary, sorts by when we happened
        // to scan it. `InspectorAttributeVisibility` already wrote the argument
        // down and never acted on it: "Created/Modified are filesystem dates,
        // which for historical material are not the date that matters."
        //
        // Sortable as of the listing routes accepting `sort_by` — which is what
        // the previous version of this comment said it was waiting for.
        //
        // `dateHeaderSortKey` is NOT the ordering. The rows come back already
        // ordered by `histdate.document_date_sort_key` (precision tie-break,
        // undated falling back to created_at-as-JDN), and
        // `LibrarySortField.orderedForDisplay` skips the client sort entirely
        // for this field. This key path exists so the column can declare a
        // comparator at all: on macOS the Table bridges each comparator to an
        // AppKit sort descriptor resolved against a column, and a descriptor
        // that maps back to nothing is the crash class from #4282.
        //
        // So the header is clickable, the click round-trips to the engine, and
        // the key path never orders a row.
        TableColumn("Date", value: \.document.dateHeaderSortKey) { node in
            documentColumnCell(for: node, columnId: "documentDate")
        }
        .width(min: 90, ideal: 130)
        .customizationID("documentDate")

        // #4482: restored now that nesting the entity columns freed slots. Both
        // were dropped only because `TableColumnBuilder` caps at 10 children —
        // a compiler arity limit deciding the app's column set — and both
        // already have cells in `tableCellView`, so this is wiring, not new UI.
        //
        // Hidden by default, like the entity columns: available in the native
        // column-header menu without adding default clutter.
        //
        // `path` was deliberately NOT restored. The engine may be remote, so a
        // local path is a lie on any other host (the no-local-paths rule);
        // `artifacts` overlaps the six per-type columns and wants a decision
        // rather than a default. Both remain on #4482.
        TableColumn("Modified", value: \.document.updatedAt) { node in
            documentColumnCell(for: node, columnId: "modifiedDate")
        }
        .width(min: 80, ideal: 100)
        .customizationID("modifiedDate")
        .defaultVisibility(.hidden)

        TableColumn("Size") { node in
            documentColumnCell(for: node, columnId: "size")
        }
        .width(min: 70, ideal: 90)
        .customizationID("size")
        .defaultVisibility(.hidden)

        // Per-entity-type columns (#519), nested as ONE child.
        //
        // SwiftUI's `TableColumnBuilder` caps at 10 direct children, and this
        // builder was at exactly 10 — the existing comment records that
        // path/modifiedDate/size/artifacts were dropped to fit. Grouping the six
        // entity columns into their own `TableColumnContent` costs one child
        // instead of six, so the cap stops dictating which columns the library
        // may have.
        entityTypeColumns
    }

    /// The six per-entity-type columns (#519), extracted so the outline builder
    /// spends one of its ten children rather than six. Each renders FlowLayout
    /// lozenges via `ArtifactEntityCell`; all hidden by default, opt-in through
    /// the native column-header menu.
    @TableColumnBuilder<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>>
    private var entityTypeColumns:
        some TableColumnContent<LibraryOutlineNode, KeyPathComparator<LibraryOutlineNode>> {
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

    /// Document row's name cell — split out of `outlineNameCell` to keep that
    /// function inside the body-length limit.
    private func documentNameCell(for document: Document) -> some View {
        // Folder name-cells accept in-app item drops (#4124) — same
        // per-cell modifier as icon/list modes; Table scopes the
        // dropDestination (and its highlight) to this cell.
        tableCellView(for: "name", document: document)
            // Document rows drag out like list/icon rows (#4160 step 3):
            // real file copy + RTF via the shared LibraryItemDrag —
            // previously only CHILD rows were draggable in table mode.
            // Same lozenge preview as list/columns rows (#26/#133-136):
            // the default cell snapshot read as a bare text scrap.
            .draggable(libraryItemDrag(for: document)) {
                RowDragPreview(
                    name: document.name,
                    systemImage: document.fileType?.icon ?? document.docType.icon
                )
            }
            .modifier(LibraryFolderCellDrop(
                acceptsDrop: document.acceptsItemDrops,
                onDropProviders: { providers in
                    handleFolderCellDrop(providers, into: document)
                }
            ))
// NO hover wash here (V4, 2026-08-09): native Table has no row-hover
            // seam, and a NAME-CELL-only wash read as a bug beside the row modes.)
            // Same look-ahead window list/icon modes use (#4160): now that the
            // name cell renders a thumbnail, without this the table fetches one
            // image per row on scroll (#4202).
            .onAppear {
                scheduleThumbnailPrefetch(around: document.id)
            }
            // VoiceOver/XCUITest parity with list rows and icon tiles.
            .accessibilityIdentifier("libraryTableRow.\(document.id)")
            .accessibilityAddTraits(selection.contains(document.id) ? .isSelected : [])
    }

    /// Artifact child-row name cell — split out of `outlineNameCell` for the
    /// function-body-length budget.
    @ViewBuilder
    private func artifactNameCell(for artifact: Artifact) -> some View {
                Label(
                    artifact.stepName ?? artifact.artifactType,
                    systemImage: "shippingbox"
                )
                .font(.subheadline)
                .foregroundStyle(.primary)
                // Same env-free preview contract as the group row above.
                .draggable(LibraryItemDrag(
                    kind: .artifact,
                    id: artifact.id,
                    documentId: artifact.documentId,
                    text: artifact.content?.isEmpty == false
                        ? artifact.content ?? artifact.artifactTypeDisplayName
                        : artifact.artifactTypeDisplayName
                )) {
                    RowDragPreview(
                        name: artifact.stepName ?? artifact.artifactType,
                        systemImage: "shippingbox"
                    )
                }
    }

    /// Name-column cell. Documents render the existing name cell; child-group rows
    /// show a count summary ("12 entities"); page/artifact items show their own label.
    @ViewBuilder
    private func outlineNameCell(for node: LibraryOutlineNode) -> some View {
        switch node.kind {
        case .document:
            documentNameCell(for: node.document)
        case .childGroup(let type):
            Label(type.groupLabel(count: node.count), systemImage: type.systemImage)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                // Explicit env-free preview — the DEFAULT preview re-hosts
                // the row with NO environment and crashes on first drag
                // (Daniel's table-view crash, 2026-08-10: EnvironmentObjectKey
                // force-unwrap under PasteboardUtility.File). See
                // DragPreviewLabel's contract.
                .draggable(LibraryItemDrag(
                    kind: .group,
                    id: node.id,
                    documentId: node.document.id,
                    text: type.groupLabel(count: node.count)
                )) {
                    RowDragPreview(
                        name: type.groupLabel(count: node.count),
                        systemImage: type.systemImage
                    )
                }
        case .pageItem(let page):
            // `pageThumbnailLabel ?? name` is nil exactly for a page with no
            // sequence — the case with no page number to show — so it fell
            // through to the storage name precisely when it mattered (#4416).
            // DocumentTitle composes the same "Page N" and degrades honestly.
            Label(
                DocumentTitle.displayName(for: page),
                systemImage: "doc.richtext"
            )
            .font(.subheadline)
            .foregroundStyle(.primary)
            .draggable(libraryItemDrag(for: page)) {
                RowDragPreview(
                    name: DocumentTitle.displayName(for: page),
                    systemImage: "doc.richtext"
                )
            }
        case .artifactItem(let artifact):
            artifactNameCell(for: artifact)
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
                .modifier(tableCellServiceInjection)
        case .childGroup, .pageItem, .artifactItem, .entityItem, .claimItem:
            EmptyView()
        }
    }

    /// SwiftUI `Table` cells are their OWN hosting boundary on macOS 26 —
    /// custom @Observable environment objects DON'T reach the cell content,
    /// so the Output/entity cells' non-optional
    /// `@Environment(ArtifactService.self)` read killed the process the
    /// moment table mode rendered a document row (Daniel's live-test crash,
    /// 2026-08-09: "Fatal error: No Observable object of type
    /// ArtifactService found"). Re-inject the ONE service list per cell —
    /// the same boundary treatment `.inspector`, sheets, and preview hosts
    /// already get (LibraryServiceEnvironment).
    var tableCellServiceInjection: TableCellServiceInjection {
        TableCellServiceInjection(
            library: libraryManager.getLibrary(id: windowState.libraryId)
                ?? libraryManager.globalLibrary
        )
    }
}

// Column definitions render inside the same whole-mode canvas as the table
// view (Daniel, 2026-08-09: every view-mode file previews in place).
#Preview("Table mode — columns") { LibraryPreviewFixtures.mode(.table, .table) }
