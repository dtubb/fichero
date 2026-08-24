import SwiftUI

// MARK: - The Data view mode's shell (datasets Stage 2)

/// The shared shell for the dataset renderers — each mounted as its OWN
/// top-level view mode. Renderers read ROLES (title/date/geo/media/subtitle)
/// derived from the page's prototype declarations; a renderer whose role has
/// no declared attribute says so instead of rendering blank.
struct DatasetModeView: View {
    /// Which renderer this mode shows — each is its own top-level view mode
    /// (Daniel 2026-08-14); this shell only hosts the shared load + status.
    let renderer: DatasetRenderer
    let folderId: String?
    /// Active search's hit ids; nil = no search. Scopes the dataset query so
    /// data views show ONLY hits (the "91 results over 4,237 items" defect).
    var searchHitIds: [String]?
    let documentService: DocumentService
    /// Nil disables editing (previews, closed library) — read-only is an
    /// honest state, not an error.
    var entityService: EntityService?
    var onOpen: (DatasetPage.Row) -> Void = { _ in }
    /// Open the row's SOURCE page in preview — the reference every
    /// extracted node carries (Daniel 2026-08-15: "we always want the
    /// reference. a click to it, so that it takes us to the page").
    var onOpenSource: (DatasetPage.Row) -> Void = { _ in }
    /// Bumps with the library's live change stream (DocumentStore.revision)
    /// so entries POP IN while a workflow runs (Daniel 2026-08-15: "they
    /// should be popping in on the library as they're added"). Debounced
    /// below — an event storm coalesces into one reload.
    var refreshToken: Int = 0
    /// The Run Workflow offering for card selections (Daniel 2026-08-15
    /// night: "select them, and then run svo on them"). Empty hides the menu.
    /// Feeds the pane's status line the DATASET's numbers and nouns.
    var onSelectionStatus: (DatasetSelectionStatus) -> Void = { _ in }
    /// The rows this renderer is SHOWING, in view order — what ⌘A covers here.
    /// Published upward for the same reason the selection is (Daniel,
    /// 2026-08-23: "visible surface, always"): the dataset filters by date and
    /// prototype in its own store, so the library's document list is not what
    /// the user is looking at.
    var onVisibleIds: ([String]) -> Void = { _ in }
    var workflows: [WorkflowSidebarItem] = []
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    /// The selection — SHARED with the library shell, not private to this
    /// view (Daniel's ruling, 2026-08-23: "visible surface, always").
    ///
    /// It used to be `@State private`, which meant the bottom bar's Delete and
    /// Run Workflow, and the menu bar's ⌘A and Delete, acted on the browser's
    /// selection — invisible in a dataset mode and not what the user had
    /// picked — while the context menu two inches away acted on the row they
    /// clicked. Same verb, same screen, different target set. Bound upward,
    /// every surface targets what the user can see, and the existing
    /// single-selection router keeps driving preview/reader/inspector.
    ///
    /// The same shape the canvases already use (see LibraryView's note that
    /// "Canvas/spatial selection is NOT separate state").
    @Binding var selection: Set<String>

    /// Owned by LibraryView since 2026-08-24 (the one-bottom-bar fold): the
    /// bar's facet cluster and this renderer act on the SAME store. This view
    /// still drives its lifecycle (the load/debounce tasks below).
    let store: DatasetModeStore

    var body: some View {
        VStack(spacing: 0) {
            // NO count header (Daniel, 2026-08-23): "425 items" told nobody
            // anything and painted an opaque band behind the floating head.
            // Loading/error keep a slot only while they have something to say.
            if store.isLoading || store.editErrorText != nil {
                HStack {
                    if store.isLoading { ProgressView().controlSize(.small) }
                    if let editError = store.editErrorText {
                        Label(editError, systemImage: "exclamationmark.triangle")
                            .font(.caption)
                            .foregroundStyle(.red)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                Divider()
            }
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            // The facet bar moved into the library's ONE bottom bar
            // (DatasetFilterCluster, Daniel 2026-08-24) — no second row.
        }
        // Fill the pane like every other library view mode (Daniel: "not
        // the right height like the other library views").
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: "\(folderId ?? "")|\(searchHitIds.map { "\($0.count)-\($0.hashValue)" } ?? "nosearch")") {
            await store.load(folderId: folderId, searchHitIds: searchHitIds, service: documentService)
        }
        // ONE router from selection to the other panes (2026-08-16, Daniel:
        // "changing selection in grid view doesn't change preview or reader
        // or inspector"): whichever renderer wrote the selection, a single
        // chosen row opens the document — preview shows the source page with
        // its bbox, reader the text, inspector the entry. Multi-selections
        // stay local (they are a batch, not a navigation).
        .onChange(of: selection) { _, newSelection in
            reportSelectionStatus()
            // Resolved through the store's ordered rows, never Set.first —
            // the selection-grammar rule (2026-08-09): a primary must be a
            // row the user acted on, not an arbitrary set element.
            guard newSelection.count == 1,
                  let row = store.visibleRows.first(where: { newSelection.contains($0.id) })
            else { return }
            onOpen(row)
        }
        .onChange(of: store.dateFilter) { _, _ in reportVisible() }
        .onChange(of: store.prototypeFilter) { _, _ in reportVisible() }
        .onChange(of: store.isLoading) { _, loading in
            if !loading { reportVisible() }
        }
        .task(id: refreshToken) {
            // Skip the mount tick — the folderId task above owns first load.
            guard store.page != nil else { return }
            // task(id:) cancels the pending sleep on every new tick, so a
            // burst of change events settles into ONE reload ~0.6s after the
            // last event.
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard !Task.isCancelled else { return }
            await store.load(folderId: folderId, searchHitIds: searchHitIds, service: documentService)
        }
    }

    /// Status AND the visible-id list travel together: they answer the same
    /// question ("what is this renderer showing?") and drifting apart would put
    /// ⌘A and the status line on different row sets.
    private func reportVisible() {
        reportSelectionStatus()
        onVisibleIds(store.orderedVisibleRows.map(\.id))
    }

    /// The dataset's numbers in the dataset's language: rows that carry
    /// dates count as "dates"; a single selection names its day.
    private func reportSelectionStatus() {
        let rows = store.visibleRows
        let selected = rows.filter { selection.contains($0.id) }
        let dated = rows.isEmpty ? false : rows.allSatisfy { store.dateValue(of: $0) != nil }
        let noun = dated ? "date" : "entry"
        let detail: String? = selected.count == 1 ? selected.first.map { row in
            store.dateValue(of: row).flatMap { DatasetModeStore.longDate($0) } ?? row.name
        } : nil
        onSelectionStatus(DatasetSelectionStatus(
            count: selected.count, total: rows.count, noun: noun, detail: detail
        ))
    }

    @ViewBuilder
    private var content: some View {
        if let errorText = store.errorText {
            ContentUnavailableView(
                "Couldn't Load Data",
                systemImage: "exclamationmark.triangle",
                description: Text(errorText)
            )
        } else if let page = store.page, page.rows.isEmpty, !store.isLoading {
            // ACTIONABLE, not just honest (Daniel 2026-08-15: an empty pane
            // over a folder of scans is a dead end): say what produces data.
            ContentUnavailableView(
                "No Data Yet",
                systemImage: "tray",
                description: Text(
                    "Nothing in this folder carries data yet. Run Transcribe, "
                        + "Extract Dates, or Diary Entries on it — transcripts, "
                        + "dates and typed attributes all appear here."
                )
            )
        } else if store.page != nil, store.visibleRows.isEmpty, !store.isLoading {
            // Filtered to nothing is a different answer than "no data" —
            // name the cause and the way back.
            ContentUnavailableView(
                "No Matching Rows",
                systemImage: "line.3.horizontal.decrease.circle",
                description: Text("No rows match the active filters. Clear them below to see everything again.")
            )
        } else {
            switch renderer {
            case .grid:
                DatasetGridView(store: store, entityService: entityService,
                                documentService: documentService,
                                selection: $selection,
                                onOpen: onOpen, onOpenSource: onOpenSource,
                                workflows: workflows,
                                onRunWorkflow: onRunWorkflow)
            case .cards:
                DatasetCardsView(
                    store: store, entityService: entityService,
                    documentService: documentService,
                    selection: $selection, workflows: workflows,
                    onOpen: onOpen, onOpenSource: onOpenSource,
                    onRunWorkflow: onRunWorkflow
                )
            case .timeline:
                DatasetTimelineView(store: store, selection: $selection,
                                    onOpen: onOpen, onOpenSource: onOpenSource,
                                    documentService: documentService,
                                    workflows: workflows,
                                    onRunWorkflow: onRunWorkflow)
            case .calendar:
                DatasetCalendarView(store: store, entityService: entityService,
                                    selection: $selection,
                                    onOpen: onOpen, onOpenSource: onOpenSource,
                                    documentService: documentService,
                                    workflows: workflows,
                                    onRunWorkflow: onRunWorkflow)
            case .map:
                DatasetMapView(store: store, onOpen: onOpen,
                               onOpenSource: onOpenSource,
                               documentService: documentService,
                               workflows: workflows,
                               onRunWorkflow: onRunWorkflow)
            }
        }
    }
}

/// The role a renderer needs is missing from every prototype on the page —
/// name the gap and where to fix it (the type editor), never a blank pane.
struct DatasetMissingRoleView: View {
    let role: String
    let renderer: String

    var body: some View {
        ContentUnavailableView(
            "No \(role.capitalized) Attribute",
            systemImage: "tag.slash",
            description: Text(
                "The \(renderer) view needs an attribute with the “\(role)” role. "
                    + "Add one to this folder's document type in the type editor "
                    + "(Inspector → Info → Prototype → Edit Types…)."
            )
        )
    }
}

#Preview("Missing role") {
    DatasetMissingRoleView(role: "date", renderer: "calendar")
        .frame(width: 560, height: 400)
}
