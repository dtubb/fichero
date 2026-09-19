import FicheroAPIClient
import SwiftUI

// MARK: - SPARQL query console (#3298)
//
// Recovered into its own file and window (#4705 increment 3, creative
// director 2026-06-25 ruling #2593/#2614: "SPARQL is wanted and must be made
// VISIBLE; never delete it"). Previously a sheet presented from the retired
// `OntologyBrowser` (`OntologyBrowser+Sheets.swift`) — the KG sidebar MODE
// retired, but this console is a genuinely separate, independently-tracked
// capability that must not go down with it. Depends only on `KGQueryStore`;
// no `OntologyBrowser` types.

/// The W3C SPARQL query console (#3298): a monospaced query editor seeded from
/// the server's example queries, ⌘↩ to run, results in a native grid with a
/// truncation badge. Makes the built-and-tested kg_sparql/rdflib layer visible
/// — it is a query surface, not dead code.
struct SPARQLConsoleView: View {
    /// The store is the ONLY endpoint accessor (#1863) — injected, not built
    /// here from a scraped client, so this console observes the same instance
    /// the rest of the app does. Optional (#4703 house rule: any
    /// `@Environment(<Observable>.self)` a scene root doesn't guarantee must
    /// degrade, not trap) even though the owning `Window` scene always
    /// injects it — a defensive floor, not an expectation this ever reads
    /// nil in practice.
    @Environment(KGQueryStore.self) private var store: KGQueryStore?

    @Environment(\.dismiss) private var dismiss
    @State private var queryText = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 25"

    var body: some View {
        Group {
            if let store {
                consoleBody(store: store)
            } else {
                ContentUnavailableView(
                    "SPARQL Console Unavailable",
                    systemImage: "chevron.left.forwardslash.chevron.right",
                    description: Text("The query store did not load with this window.")
                )
            }
        }
        .frame(minWidth: 640, minHeight: 520)
    }

    private func consoleBody(store: KGQueryStore) -> some View {
        VStack(spacing: 0) {
            header(store: store)
            Divider()
            editor(store: store)
            Divider()
            results(store: store)
        }
        .task { await store.loadExamples() }
    }

    private func header(store: KGQueryStore) -> some View {
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

    private func editor(store: KGQueryStore) -> some View {
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
    private func results(store: KGQueryStore) -> some View {
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

#Preview("SPARQL Console (no store — the degrade path)") {
    // `store` is optional by design (#4703 house rule), so the cheap
    // RenderPreview layer renders correctly with NO KGQueryStore injected —
    // the same "unavailable" state a scene that failed to inject one shows.
    SPARQLConsoleView()
}
