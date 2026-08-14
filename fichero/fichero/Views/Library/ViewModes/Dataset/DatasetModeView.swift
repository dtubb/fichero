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

    @State private var store = DatasetModeStore()

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
        }
        // Fill the pane like every other library view mode (Daniel: "not
        // the right height like the other library views").
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: folderId) {
            await store.load(folderId: folderId, service: documentService)
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
            ContentUnavailableView(
                "No Items",
                systemImage: "tray",
                description: Text("Nothing in this folder carries attributes yet.")
            )
        } else {
            switch renderer {
            case .grid:
                DatasetGridView(store: store, entityService: entityService, onOpen: onOpen)
            case .cards:
                DatasetCardsView(store: store, onOpen: onOpen)
            case .timeline:
                DatasetTimelineView(store: store, onOpen: onOpen)
            case .calendar:
                DatasetCalendarView(store: store, entityService: entityService, onOpen: onOpen)
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
