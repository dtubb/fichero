import SwiftUI

// MARK: - The Data view mode's shell (datasets Stage 2)

/// Hosts the four renderers behind ONE view mode — an internal switcher, not
/// four top-level modes. Renderers read ROLES (title/date/geo/media/subtitle)
/// derived from the page's prototype declarations; a renderer whose role has
/// no declared attribute says so instead of rendering blank.
struct DatasetModeView: View {
    let folderId: String?
    let documentService: DocumentService
    var onOpen: (DatasetPage.Row) -> Void = { _ in }

    @State private var store = DatasetModeStore()
    @SceneStorage("library.datasetRenderer") private var rendererRaw: String
        = DatasetRenderer.cards.rawValue

    private var renderer: DatasetRenderer {
        DatasetRenderer(rawValue: rendererRaw) ?? .cards
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("Renderer", selection: $rendererRaw) {
                    ForEach(DatasetRenderer.allCases) { option in
                        Label(option.rawValue, systemImage: option.icon)
                            .tag(option.rawValue)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 380)
                Spacer(minLength: 0)
                if store.isLoading { ProgressView().controlSize(.small) }
                if let page = store.page {
                    Text("\(page.total) item\(page.total == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            Divider()
            content
        }
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
            case .cards:
                DatasetCardsView(store: store, onOpen: onOpen)
            case .timeline:
                DatasetTimelineView(store: store, onOpen: onOpen)
            case .calendar:
                DatasetCalendarView(store: store, onOpen: onOpen)
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
