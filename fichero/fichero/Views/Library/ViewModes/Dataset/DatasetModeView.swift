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
    var workflows: [WorkflowSidebarItem] = []
    var onRunWorkflow: (String, [String], String?, String?) -> Void = { _, _, _, _ in }

    @State private var store = DatasetModeStore()
    /// Card selection — the batch a context-menu run targets.
    @State private var selection: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                if store.isLoading { ProgressView().controlSize(.small) }
                if let editError = store.editErrorText {
                    Label(editError, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                if let page = store.page {
                    Text("\(page.total) item\(page.total == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            Divider()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            if store.page?.rows.isEmpty == false {
                datasetFilterBar
            }
        }
        // Fill the pane like every other library view mode (Daniel: "not
        // the right height like the other library views").
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: folderId) {
            await store.load(folderId: folderId, service: documentService)
        }
        // ONE router from selection to the other panes (2026-08-16, Daniel:
        // "changing selection in grid view doesn't change preview or reader
        // or inspector"): whichever renderer wrote the selection, a single
        // chosen row opens the document — preview shows the source page with
        // its bbox, reader the text, inspector the entry. Multi-selections
        // stay local (they are a batch, not a navigation).
        .onChange(of: selection) { _, newSelection in
            // Resolved through the store's ordered rows, never Set.first —
            // the selection-grammar rule (2026-08-09): a primary must be a
            // row the user acted on, not an arbitrary set element.
            guard newSelection.count == 1,
                  let row = store.visibleRows.first(where: { newSelection.contains($0.id) })
            else { return }
            onOpen(row)
        }
        .task(id: refreshToken) {
            // Skip the mount tick — the folderId task above owns first load.
            guard store.page != nil else { return }
            // task(id:) cancels the pending sleep on every new tick, so a
            // burst of change events settles into ONE reload ~0.6s after the
            // last event.
            try? await Task.sleep(nanoseconds: 600_000_000)
            guard !Task.isCancelled else { return }
            await store.load(folderId: folderId, service: documentService)
        }
    }

    /// The facet strip for the rows THIS pane renders — the control lives
    /// with the surface it acts on (#4407 rule; the library mini toolbar's
    /// sort/filter act on the list view, not on these renderers). Dates +
    /// Type today; the entity facet joins here once entries carry entity
    /// links (task #31 spec).
    @ViewBuilder
    private var datasetFilterBar: some View {
        PaneFilterBar(placement: .bottom) {
            Menu {
                ForEach(DatasetDateFilter.allCases) { choice in
                    Button {
                        store.dateFilter = choice
                    } label: {
                        Text(choice.rawValue)
                        if store.dateFilter == choice {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            } label: {
                Label(
                    store.dateFilter == .all ? "Dates" : store.dateFilter.rawValue,
                    systemImage: "calendar.badge.checkmark"
                )
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Show all rows, only dated rows, or only undated rows")

            Menu {
                ForEach(DatasetModeStore.TextDetail.allCases) { choice in
                    Button {
                        store.textDetail = choice
                    } label: {
                        Text(choice.rawValue)
                        if store.textDetail == choice {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            } label: {
                Label("Text", systemImage: "text.alignleft")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Show the excerpt or the full entry text on cards")

            if store.availablePrototypes.count > 1 {
                Menu {
                    Button {
                        store.prototypeFilter = nil
                    } label: {
                        Text("All Types")
                        if store.prototypeFilter == nil {
                            Image(systemName: "checkmark")
                        }
                    }
                    Divider()
                    ForEach(store.availablePrototypes, id: \.self) { key in
                        Button {
                            store.prototypeFilter = key
                        } label: {
                            Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                            if store.prototypeFilter == key {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                } label: {
                    Label("Type", systemImage: "tag")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Show only rows of one document type")
            }

            Spacer(minLength: 8)

            if store.dateFilter != .all || store.prototypeFilter != nil {
                Text("\(store.visibleRows.count) of \(store.page?.rows.count ?? 0)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                Button("Clear") {
                    store.dateFilter = .all
                    store.prototypeFilter = nil
                }
                .buttonStyle(.borderless)
                .controlSize(.small)
                .help("Clear dataset filters")
            }
        }
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
                                selection: $selection,
                                onOpen: onOpen, onOpenSource: onOpenSource)
            case .cards:
                DatasetCardsView(
                    store: store, entityService: entityService,
                    selection: $selection, workflows: workflows,
                    onOpen: onOpen, onOpenSource: onOpenSource,
                    onRunWorkflow: onRunWorkflow
                )
            case .timeline:
                DatasetTimelineView(store: store, selection: $selection,
                                    onOpen: onOpen, onOpenSource: onOpenSource)
            case .calendar:
                DatasetCalendarView(store: store, entityService: entityService,
                                    selection: $selection,
                                    onOpen: onOpen, onOpenSource: onOpenSource)
            case .map:
                DatasetMapView(store: store, onOpen: onOpen)
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
