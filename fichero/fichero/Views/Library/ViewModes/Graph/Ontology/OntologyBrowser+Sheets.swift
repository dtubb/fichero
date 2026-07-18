import FicheroAPIClient
import SwiftUI

// Sheet + confirmation-dialog modifiers for OntologyBrowser (#1703).
// Extracted from OntologyBrowser.body so the main view stays compact;
// behavior is identical — the modifiers read/write the same `@State` on
// the browser via the passed-in value.

/// Hosts the cluster of `.sheet` / `.confirmationDialog` modifiers for
/// the browser.
struct OntologySheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .modifier(OntologyEntitySheetsModifier(browser: browser))
            .confirmationDialog(
                "Delete this entity?",
                isPresented: Binding(
                    get: { browser.entityPendingDeletion != nil },
                    set: { if !$0 { browser.entityPendingDeletion = nil } }
                ),
                presenting: browser.entityPendingDeletion
            ) { entity in
                Button("Delete \(entity.canonicalName)", role: .destructive) {
                    Task { await browser.deleteEntity(entity) }
                }
                Button("Cancel", role: .cancel) { browser.entityPendingDeletion = nil }
            } message: { _ in
                Text("The entity will be removed along with any claims that reference it (#901).")
            }
            // W3C SPARQL query console (#3298).
            .sheet(isPresented: Binding(
                get: { browser.showSparqlConsole },
                set: { browser.showSparqlConsole = $0 }
            )) {
                KGQueryConsoleView()
            }
    }
}

/// The create / edit / merge / split / predictions sheets. Split out of
/// `OntologySheetsModifier` (#1703) and further chained across two
/// modifiers so each body stays within SwiftLint's function-length limit
/// — behavior is unchanged.
private struct OntologyEntitySheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .modifier(OntologyCreateEditSheetsModifier(browser: browser))
            .modifier(OntologyMergeSplitSheetsModifier(browser: browser))
    }
}

/// Predictions review + create + edit sheets.
private struct OntologyCreateEditSheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .sheet(item: Binding(
                get: { browser.pendingPredictions.map(IdentifiedPredictions.init) },
                set: { newValue in browser.pendingPredictions = newValue?.response }
            )) { wrapped in
                HeuristicReviewSheet(response: wrapped.response) {
                    browser.pendingPredictions = nil
                }
            }
            .sheet(isPresented: Binding(
                get: { browser.showCreateSheet },
                set: { browser.showCreateSheet = $0 }
            )) {
                NewEntitySheet { newEntity in
                    browser.selectedEntityId = newEntity.id
                    browser.showCreateSheet = false
                    Task { await browser.loadEntities() }
                }
            }
            .sheet(item: Binding(
                get: { browser.entityPendingEdit.map(IdentifiedEntity.init) },
                set: { browser.entityPendingEdit = $0?.entity }
            )) { wrapped in
                NewEntitySheet(editing: wrapped.entity) { _ in
                    browser.entityPendingEdit = nil
                    Task { await browser.loadEntities() }
                }
            }
    }
}

/// Merge + split sheets.
private struct OntologyMergeSplitSheetsModifier: ViewModifier {
    let browser: OntologyBrowser

    func body(content: Content) -> some View {
        content
            .sheet(item: Binding(
                get: { browser.entityPendingMerge.map(IdentifiedEntity.init) },
                set: { browser.entityPendingMerge = $0?.entity }
            )) { wrapped in
                EntityMergeSheet(
                    absorbingEntity: wrapped.entity,
                    allEntities: browser.entities
                ) {
                    browser.entityPendingMerge = nil
                    Task { await browser.loadEntities() }
                }
            }
            .sheet(item: Binding(
                get: { browser.entityPendingSplit.map(IdentifiedEntity.init) },
                set: { browser.entityPendingSplit = $0?.entity }
            )) { wrapped in
                EntitySplitSheet(
                    primaryEntity: wrapped.entity,
                    allEntities: browser.entities
                ) {
                    browser.entityPendingSplit = nil
                    Task { await browser.loadEntities() }
                }
            }
    }
}

// MARK: - SPARQL query console (#3298)

/// The W3C SPARQL query console (#3298): a monospaced query editor seeded from
/// the server's example queries, ⌘↩ to run, results in a native grid with a
/// truncation badge. Makes the built-and-tested kg_sparql/rdflib layer visible
/// — it is a query surface, not dead code.
struct KGQueryConsoleView: View {
    /// The store is the ONLY endpoint accessor (#1863) — injected, not built
    /// here from a scraped client, so this console observes the same instance
    /// the rest of the app does.
    @Environment(KGQueryStore.self) private var store

    @Environment(\.dismiss) private var dismiss
    @State private var queryText = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 25"

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            editor
            Divider()
            results
        }
        .frame(minWidth: 640, minHeight: 520)
        .task { await store.loadExamples() }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Label("SPARQL Console", systemImage: "chevron.left.forwardslash.chevron.right")
                .font(.headline)
            Spacer()
            if !store.examples.isEmpty {
                Menu("Examples") {
                    ForEach(store.examples, id: \.id) { example in
                        Button(example.title) { queryText = example.query }
                            .help(example.description)
                    }
                }
                .fixedSize()
            }
            Button("Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(12)
    }

    private var editor: some View {
        VStack(spacing: 6) {
            TextEditor(text: $queryText)
                // Monospaced is an intentional non-semantic use — SPARQL is code.
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 120)
                .overlay(alignment: .bottomTrailing) {
                    Button {
                        Task { await store.run(query: queryText) }
                    } label: {
                        Label("Run", systemImage: "play.fill")
                    }
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(store.isRunning)
                    .padding(8)
                }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var results: some View {
        if store.isRunning {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = store.errorMessage {
            ContentUnavailableView {
                Label("Query error", systemImage: "exclamationmark.triangle")
            } description: {
                Text(error).font(.system(.callout, design: .monospaced))
            }
        } else if let response = store.response {
            VStack(alignment: .leading, spacing: 0) {
                resultsSummary(response)
                Divider()
                resultsGrid(response)
            }
        } else {
            ContentUnavailableView(
                "No results yet",
                systemImage: "tablecells",
                description: Text("Write a SPARQL query and press ⌘↩ to run it.")
            )
        }
    }

    private func resultsSummary(_ response: Components.Schemas.SparqlResponse) -> some View {
        HStack(spacing: 8) {
            Text("\(response.rowCount) row\(response.rowCount == 1 ? "" : "s")")
                .font(.caption).foregroundStyle(.secondary)
            Text("· \(response.elapsedMs) ms")
                .font(.caption).foregroundStyle(.secondary)
            if response.truncated {
                Text("truncated")
                    .font(.caption2)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(.orange.opacity(0.18), in: Capsule())
                    .foregroundStyle(.orange)
                    .help("More rows exist than were returned")
            }
            Spacer()
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
    }

    private func resultsGrid(_ response: Components.Schemas.SparqlResponse) -> some View {
        let columns = KGQueryStore.columnKeys(response.rows)
        return ScrollView([.vertical, .horizontal]) {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                GridRow {
                    ForEach(columns, id: \.self) { key in
                        Text(key).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    }
                }
                Divider()
                ForEach(Array(response.rows.enumerated()), id: \.offset) { _, row in
                    GridRow {
                        ForEach(columns, id: \.self) { key in
                            Text(KGQueryStore.value(row, forKey: key))
                                .font(.system(.callout, design: .monospaced))
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .padding(12)
        }
    }
}
