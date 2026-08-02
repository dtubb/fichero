import FicheroAPIClient
import OSLog
import SwiftUI

private let relatedLogger = Logger(
    subsystem: "app.fichero.fichero", category: "RelatedDocumentsTab"
)

/// Automatic see-also for the open document (#4120): shared knowledge-graph
/// entities and/or semantic embedding neighbors, ranked best-first by the
/// engine. Relevance renders as a bar, not a number (#4119) — the underlying
/// cosine similarity is real, so the bar is honest.
struct DocumentInspectorRelatedTab: View {
    let document: Document
    var onNavigateToSource: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore

    /// Keyboard-navigable selection (#4483).
    ///
    /// Without a `selection:` binding a `List` is a stack of tappable rows:
    /// macOS gives it no arrow keys, no focus ring, no type-select and no
    /// context menu. This tab was the only inspector list in that state — and
    /// the rule against it is written down in its siblings' own doc comments
    /// ("Native `List(selection:)`, NOT a hand-rolled `VStack` of tappable
    /// rows", ArtifactListView:12 / CitationListView:13).
    ///
    /// Single, not `Set`: no operation here acts on several rows — the tab
    /// navigates to one document. Multi-select would be an affordance for
    /// nothing.
    @State private var selectedDocumentId: String?

    @State private var items: [Components.Schemas.RelatedDocumentsResponse] = []
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        Group {
            if isLoading && items.isEmpty {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadError {
                // A failed lookup is an error, never a silent empty (#4109 ethos).
                Label(loadError, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .padding()
            } else if items.isEmpty {
                ContentUnavailableView(
                    "No Related Documents",
                    systemImage: "doc.on.doc",
                    description: Text(
                        "Related documents appear once this library has embeddings or extracted entities."
                    )
                )
            } else {
                List(items, id: \.documentId, selection: $selectedDocumentId) { item in
                    relatedRow(item)
                        .inspectorListRowTarget()
                        // Select on single click (the List's job), OPEN on
                        // double-click — the same open-vs-select split
                        // `ArtifactListView` uses. Navigating on selection
                        // change would mean arrow-keying through the list
                        // reloaded the whole content pane on every keystroke.
                        .onTapGesture(count: 2) {
                            navigate(to: item.documentId)
                        }
                        .contextMenu {
                            Button("Open Document") {
                                navigate(to: item.documentId)
                            }
                        }
                }
                .listStyle(.inset)
            }
        }
        .task(id: document.id) {
            await load()
        }
    }

    /// The one place this tab navigates from, so the double-click and the
    /// context menu cannot drift apart.
    private func navigate(to documentId: String) {
        selectedDocumentId = documentId
        onNavigateToSource?(documentId)
    }

    @ViewBuilder
    private func relatedRow(_ item: Components.Schemas.RelatedDocumentsResponse) -> some View {
        HStack(spacing: 8) {
            Image(systemName: item.docType == "folder" ? "folder" : "doc.text")
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.name ?? item.documentId)
                    .font(.body)
                    .lineLimit(1)

                let entityNames = item.sampleEntityNames ?? []
                if !entityNames.isEmpty {
                    Text(entityNames.joined(separator: " · "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                } else if item.similarity != nil {
                    Text("Similar content")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Graphical relevance (#4119): a real cosine similarity as a bar,
            // never a percentage number.
            if let similarity = item.similarity {
                ProgressView(value: max(0, min(1, similarity)))
                    .progressViewStyle(.linear)
                    .frame(width: 48)
                    .tint(.accentColor)
                    .accessibilityLabel("Relevance")
            } else if item.sharedEntities > 0 {
                Text("\(item.sharedEntities)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(Color.secondary.opacity(0.12)))
                    .help("\(item.sharedEntities) shared entities")
            }
        }
    }

    @MainActor
    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            items = try await documentStore.documentService.getRelatedDocuments(document.id)
        } catch {
            if (error as? CancellationError) != nil { return }
            relatedLogger.error("related fetch failed: \(error.localizedDescription)")
            loadError = "Couldn't load related documents: \(error.localizedDescription)"
            items = []
        }
    }
}
