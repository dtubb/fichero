import FicheroAPIClient
import SwiftUI

// MARK: - Miller Columns (Finder-style column browser, #4160 step 4)
//
// An ADDITIONAL view mode beside the table's 3-level outline (the user's
// decision) — not a replacement. Column 0 shows the browsed folder's
// contents (exactly the list view's document set); each path segment opens
// the next column with that folder's children, fetched through the EXISTING
// `DocumentStore.children(of:)` (no parallel store). ONE column is active at
// a time and binds the existing selection model (`selection` /
// `selectionAnchor` / `selectionCursor` / `LibraryKeyboardCursor`); ancestor
// columns show their path segment as a passive Mail-style highlight (#4191).
//
// The preview column (source-viewer for a selected non-folder) lands as a
// follow-up commit — columns first, per review.

extension LibraryView {
    /// The columns whose ids survived live resolution this render: the path
    /// prefix whose every segment still resolves to a live folder in the
    /// children cache or the browsed list.
    var columnsLivePath: [String] {
        MillerColumnModel.livePath(columnsPath) { id in
            columnsResolveFolder(id) != nil
        }
    }

    /// Resolve a path segment to its LIVE document — the browsed list first
    /// (root-column segments), then the children cache (deeper segments).
    private func columnsResolveFolder(_ id: String) -> Document? {
        let doc = filteredDocuments.first { $0.id == id }
            ?? columnsChildren.values.lazy.compactMap({ $0.first { $0.id == id } }).first
        return doc?.docType == .folder ? doc : nil
    }

    /// The documents of column `depth`: 0 = the browsed set, deeper = the
    /// cached children of the path segment above it.
    func columnsDocuments(atDepth depth: Int) -> [Document] {
        guard depth > 0 else { return filteredDocuments }
        let path = columnsLivePath
        guard depth <= path.count else { return [] }
        return columnsChildren[path[depth - 1]] ?? []
    }

    /// The trailing preview column's document: a SINGLE selected non-folder,
    /// wherever it lives in the open columns. Multi-select or a folder
    /// selection shows no preview column (Finder behavior — folders disclose
    /// their children instead).
    var columnsPreviewDocument: Document? {
        // orderedPrimarySelectionId, not `selection.first` (rule 2 of the
        // selection-grammar guardrail, 2026-08-09): the count==1 guard made
        // .first deterministic HERE, but this was the one resolver on the
        // wrong seam — and the guardrail now forbids the shape outright so
        // the next reader doesn't copy it somewhere unguarded.
        guard selection.count == 1,
              let id = orderedPrimarySelectionId,
              let doc = navigableDocument(for: id),
              doc.docType != .folder else { return nil }
        return doc
    }

    /// The active column's documents — what the keyboard navigates over.
    var columnsActiveDocuments: [Document] {
        columnsDocuments(atDepth: MillerColumnModel.clampActiveDepth(
            columnsActiveDepth, pathCount: columnsLivePath.count
        ))
    }

    var columnsView: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal) {
                HStack(spacing: 0) {
                    let path = columnsLivePath
                    ForEach(0...path.count, id: \.self) { depth in
                        millerColumn(depth: depth, path: path)
                            .frame(width: 240)
                        Divider()
                    }
                    // Finder's trailing preview column: a SINGLE selected
                    // non-folder shows in the EXISTING Preview surface
                    // (EditorView = the source viewer — no derived knowledge,
                    // no editing; Reader/Inspector stay separate surfaces).
                    // Stable id keeps the mount across doc flips (#788).
                    if let previewDoc = columnsPreviewDocument {
                        EditorView(document: previewDoc)
                            .id("columns.preview")
                            .frame(width: 320)
                            .accessibilityIdentifier("libraryColumnPreview")
                        Divider()
                    }
                }
            }
            // Same rationale as list mode (#575/#4160): .focusable() so the
            // body-level .onKeyPress handlers receive arrows/Return/type-
            // select; the container ring is suppressed, selection is focus.
            .focusable()
            .focusEffectDisabled()
            .task(id: columnsPath) {
                await loadColumnsChildren()
            }
            // A document.* change can add/remove/rename anything mid-path —
            // refetch the open columns so they never go stale (#3249 class).
            .onChange(of: documentStore.currentDocuments) { _, _ in
                Task { @MainActor in await loadColumnsChildren(force: true) }
            }
            .onChange(of: listScrollTarget) { _, id in
                guard let id else { return }
                proxy.scrollTo(id, anchor: nil)
                listScrollTarget = nil
            }
        }
    }

    /// One column of the browser. Rows are COMPACT single-liners (icon +
    /// name + disclosure chevron, Finder-style), so uniform density is
    /// structural — no reserved multi-line blocks needed here.
    @ViewBuilder
    private func millerColumn(depth: Int, path: [String]) -> some View {
        let docs = columnsDocuments(atDepth: depth)
        let isActiveColumn = depth == MillerColumnModel.clampActiveDepth(
            columnsActiveDepth, pathCount: path.count
        )
        // Hand-rolled ScrollView+LazyVStack ON PURPOSE (native-controls
        // baseline): `List` is NSTableView-backed and consumes arrow keys
        // before `.onKeyPress` fires, and this browser's entire keyboard
        // model — ↑/↓ within the ACTIVE column, ←/→ BETWEEN columns via
        // handleColumnsArrowKey, one shared cursor across all columns —
        // runs through the body-level key handlers. A per-column List
        // would also own per-column selection, breaking the single shared
        // selection set. What List gives free is provided explicitly:
        // selection (LibrarySelectableRow), a11y (combined elements +
        // libraryColumnRow identifiers), hover (LibraryRowHoverWash).
        // Same constraint as list mode's sanctioned entry.
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(docs) { doc in
                    // Hoisted (V6, 2026-08-09): the SAME selected-looking
                    // predicate feeds the fill AND the hover gate — hovering
                    // an ancestor path segment used to wash a row that was
                    // painted selected, because the hover gate only asked
                    // about the live selection.
                    let rowLooksSelected = (isActiveColumn && selection.contains(doc.id))
                        || (!isActiveColumn && path.indices.contains(depth) && path[depth] == doc.id)
                    LibrarySelectableRow(
                        identity: ColumnRowIdentity(
                            document: doc,
                            depth: depth,
                            isPathSegment: path.indices.contains(depth) && path[depth] == doc.id,
                            isRenaming: renamingDocumentId == doc.id
                        ),
                        // Active-column rows carry the live selection; an
                        // ancestor's path segment stays the passive GREY
                        // trail marker (Finder) — `focused: false` keeps it
                        // out of the accent grammar by construction.
                        isSelected: rowLooksSelected,
                        tint: isActiveColumn ? selectionTint : .secondary,
                        focused: isActiveColumn && isPaneFocused
                    ) {
                        millerRow(doc, depth: depth, isActiveColumn: isActiveColumn)
                    }
                    .equatable()
                    .modifier(LibraryRowHoverWash(enabled: !rowLooksSelected))
                    .id(doc.id)
                    .draggable(libraryItemDrag(for: doc)) {
                        DragPreviewLabel(name: doc.name, systemImage: doc.fileType?.icon ?? doc.docType.icon)
                    }
                    .modifier(LibraryFolderCellDrop(
                        acceptsDrop: doc.acceptsItemDrops,
                        onDropProviders: { providers in handleFolderCellDrop(providers, into: doc) }
                    ))
                    .onTapGesture(count: 2) { handleDoubleClick(doc) }
                    .onTapGesture { handleColumnTap(doc, depth: depth) }
                    .contextMenu { documentContextMenu(for: doc) }
                }
            }
        }
        // Click in a column's empty space deselects, like Finder (#4160).
        // Through `apply(clear())`, not three assignments: list and icon mode
        // already clear this way, and three modes hand-writing the same three
        // fields is how one of them ends up writing only two (#4436).
        .onTapGesture {
            apply(SelectionGrammar.clear())
        }
    }

    @ViewBuilder
    private func millerRow(_ doc: Document, depth: Int, isActiveColumn: Bool) -> some View {
        HStack(spacing: 8) {
            // One glyph per node, from the same ladder the sidebar reads
            // (#4516) — this used to be a two-way folder/doc.text split, which
            // is why a workflow mirror row read as a plain text document.
            Image(systemName: doc.displaySymbol())
                .symbolVariant(doc.docType == .folder ? .fill : .none)
                .symbolRenderingMode(doc.isLockedSystemNode ? .hierarchical : .monochrome)
                .foregroundStyle(columnRowTint(doc))
                .frame(width: 16)
            if renamingDocumentId == doc.id {
                EditableDocumentName(
                    document: doc,
                    isRenaming: true,
                    editingName: $editingName,
                    font: .body,
                    onCommit: commitRename,
                    onCancel: cancelRename
                )
            } else {
                // #4416: `pageThumbnailLabel ?? doc.name` reads like a defence
                // and is not one — the label is nil exactly when a page has no
                // sequence, so it fell through to the storage filename in the
                // one case it was supposed to cover.
                Text(DocumentTitle.displayName(for: doc))
                    .font(.body)
                    .foregroundStyle(
                        isActiveColumn && selection.contains(doc.id)
                            ? LibrarySelectionStyle.labelTint(focused: isPaneFocused)
                            : .primary
                    )
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .help(DocumentTitle.displayName(for: doc))
            }
            Spacer(minLength: 0)
            if doc.docType == .folder {
                Image(systemName: "chevron.right")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 3)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            doc.docType == .folder
                ? "\(DocumentTitle.displayName(for: doc)), folder"
                : DocumentTitle.displayName(for: doc)
        )
        .accessibilityAddTraits(selection.contains(doc.id) ? .isSelected : [])
        .accessibilityIdentifier("libraryColumnRow.\(doc.id)")
    }

    /// Purple for a system-owned node, matching the sidebar's locked rows
    /// (#4514); accent for a folder the user owns; secondary for a leaf.
    private func columnRowTint(_ doc: Document) -> Color {
        if doc.isLockedSystemNode { return .purple }
        return doc.docType == .folder ? .accentColor : .secondary
    }

    /// Click semantics: select in THIS column (which becomes active); a
    /// folder click also discloses its children in the next column, a
    /// document click closes deeper columns.
    ///
    /// OPENING and CLOSING columns is a PLAIN-click behaviour only (#4377).
    /// `handleTap` already refuses to drill into a container when ⇧ or ⌘ is
    /// held — a modified click is building a selection, and navigating away
    /// mid-build throws it out — but this wrapper used to descend or truncate
    /// the column path *unconditionally, one call before that guard ran*. So
    /// ⌘-clicking a folder to add it to a selection also opened it, and
    /// ⇧-clicking a document closed every deeper column. The guard was real
    /// and this path went around it.
    ///
    /// `columnsActiveDepth` deliberately still moves on a modified click: it
    /// opens and closes nothing, and it is what makes the clicked column the
    /// active one. Freezing it would let a ⌘-click land in a column that
    /// `millerRow` then renders UNSELECTED — the row only shows its selection
    /// while its column is active — so the gesture would silently appear to do
    /// nothing.
    ///
    /// A ⇧-click in a DIFFERENT column therefore ranges over the newly-active
    /// column, where the old anchor does not appear, and `SelectionGrammar`
    /// degrades it to selecting that one row. That is the intended degrade, not
    /// a gap: a range spanning two Miller columns has no meaning, which is the
    /// same reason ←/→ are not `SelectionGrammar.click`.
    func handleColumnTap(_ doc: Document, depth: Int) {
        onRequestFocus()
        columnsActiveDepth = depth
        guard Self.columnTapOpensOrClosesColumns(modifiers: currentSelectionModifiers) else {
            handleTap(doc)
            return
        }
        if doc.docType == .folder {
            columnsPath = MillerColumnModel.descend(path: columnsLivePath, atDepth: depth, into: doc.id)
        } else {
            columnsPath = MillerColumnModel.truncate(path: columnsLivePath, forSelectionAtDepth: depth)
        }
        handleTap(doc)
    }

    /// Whether a columns click may open or close columns — i.e. write
    /// `columnsPath` (#4377). NOT about which column is active, which a
    /// modified click still moves.
    ///
    /// Pure and `nonisolated` for the same reason `plainTapNavigatesInto` is:
    /// it is a rule, the rule was being applied in the wrong ORDER relative to
    /// the grammar, and a rule with no seam has no regression test. Its whole
    /// content is "only a plain click navigates" — which is already what
    /// `handleTap` believes about drilling in, and was not what the columns
    /// wrapper did about opening and closing columns.
    nonisolated static func columnTapOpensOrClosesColumns(
        modifiers: SelectionGrammar.Modifiers
    ) -> Bool {
        modifiers.isEmpty
    }

    /// Land the columns cursor on one row of the newly-active column.
    ///
    /// ←/→ are DELIBERATELY not `SelectionGrammar.click`: they change which
    /// column is active, which changes the ordered list itself, so there is no
    /// list for a ⇧-range to span — a range across two columns has no meaning,
    /// the same reason `click` degrades to a single selection for an id it
    /// cannot find. What they must still do is move all three fields together,
    /// which is what this goes through `apply` for (#4436).
    private func selectColumnRow(_ id: String) {
        apply(SelectionGrammar.select(id))
        listScrollTarget = id
    }

    /// Columns-mode arrow handling: ↑/↓/Home/End run the SHARED cursor logic
    /// over the active column's ids; → descends into the selected folder,
    /// ← re-activates the parent column (path preserved, Finder semantics).
    func handleColumnsArrowKey(direction: ArrowDirection) -> KeyPress.Result {
        let path = columnsLivePath
        let depth = MillerColumnModel.clampActiveDepth(columnsActiveDepth, pathCount: path.count)
        switch direction {
        case .right:
            guard let primaryId = orderedPrimarySelectionId,
                  let doc = columnsActiveDocuments.first(where: { $0.id == primaryId }),
                  doc.docType == .folder else { return .handled }
            columnsPath = MillerColumnModel.descend(path: path, atDepth: depth, into: doc.id)
            columnsActiveDepth = depth + 1
            if let firstChild = columnsChildren[doc.id]?.first {
                selectColumnRow(firstChild.id)
            } else {
                // Children not fetched yet — the column opens empty and the
                // .task fills it; selection stays on the folder until then.
                // This branch used to write ONLY `selection`, leaving the
                // anchor and cursor pointing at the row you came from, so the
                // next ⇧-click extended from a different column (#4436).
                selectColumnRow(doc.id)
            }
            return .handled
        case .left:
            guard depth > 0 else { return .handled }
            columnsActiveDepth = depth - 1
            // The parent column's cursor is the path segment that opened us.
            selectColumnRow(path[depth - 1])
            return .handled
        default:
            return .ignored   // ↑/↓/page/home/end fall through to the shared handler
        }
    }

    /// Fetch children for every open path segment (and refresh on library
    /// change events). DocumentStore.children(of:) is cached + status-
    /// overridden, so this stays cheap on re-runs.
    @MainActor
    func loadColumnsChildren(force: Bool = false) async {
        for folderId in columnsPath {
            if !force, columnsChildren[folderId] != nil { continue }
            columnsChildren[folderId] = await documentStore.children(of: folderId)
        }
    }
}
