import FicheroAPIClient
import Foundation
import SwiftUI

// MARK: - Enrich-from-Wikidata affordance (#3757 follow-on)

/// Header button that opens the Wikidata enrichment sheet. Self-contained (owns
/// its own presentation state) so it drops into `EntityDetailView` with a single
/// line next to `authorityLinkButton` — enrichment builds on the same authority
/// link, so it sits with it. Enabled once the entity has an id; the sheet itself
/// reports (honestly) when there is no linked Wikidata QID to enrich from.
struct EnrichFromWikidataButton: View {
    let entity: Components.Schemas.KnowledgeEntity
    let entityStore: EntityStore

    @State private var showSheet = false

    var body: some View {
        Button {
            showSheet = true
        } label: {
            Label("Enrich from Wikidata", systemImage: "sparkles")
                .font(.caption)
        }
        .buttonStyle(.bordered)
        .disabled(entity.id == nil)
        .help("Import selected Wikidata statements as claims, marked Wikidata-sourced")
        .sheet(isPresented: $showSheet) {
            WikidataEnrichmentSheet(entity: entity, entityStore: entityStore)
        }
    }
}

/// Review-and-import panel for a linked entity's Wikidata statements. All
/// endpoint access goes through `EntityStore` (observable-data-layer): this sheet
/// reads the returned preview and dispatches the import — it never calls a
/// service directly.
///
/// Provenance is load-bearing: imported claims are marked WIKIDATA-SOURCED on the
/// server (no `source_document_id`), and this panel says so plainly — the imported
/// statements are external assertions, not something read in this corpus.
struct WikidataEnrichmentSheet: View {
    @Environment(\.dismiss) private var dismiss
    let entity: Components.Schemas.KnowledgeEntity
    let entityStore: EntityStore

    @State private var preview: WikidataEnrichmentPreview?
    @State private var selection: Set<String> = []
    @State private var isLoading = false
    @State private var isImporting = false
    @State private var statusMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Enrich from Wikidata")
                .font(.headline)
            Text("Import selected Wikidata statements about “\(entity.canonicalName)” as claims. Imported claims are marked Wikidata-sourced — external assertions, not read in this corpus.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let preview, !preview.qid.isEmpty {
                Label("Wikidata \(preview.qid)", systemImage: "globe")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            content

            HStack {
                if let statusMessage {
                    Text(statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                Button("Close") { dismiss() }
                Button {
                    Task { await importSelected() }
                } label: {
                    if isImporting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Import \(selection.count) selected")
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(selection.isEmpty || isImporting)
            }
        }
        .padding(20)
        .frame(width: 560, height: 500)
        .task { await load() }
    }

    @ViewBuilder
    private var content: some View {
        if isLoading {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let preview, !preview.statements.isEmpty {
            List(preview.statements) { statement in
                statementRow(statement)
            }
            .frame(minHeight: 240)
        } else {
            VStack(spacing: 8) {
                Image(systemName: "tray")
                    .font(.largeTitle)
                    .foregroundStyle(.secondary)
                Text(statusMessage ?? "No Wikidata statements to import.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func statementRow(_ statement: WikidataStatementRow) -> some View {
        Button {
            toggle(statement.id)
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Image(systemName: selection.contains(statement.id) ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selection.contains(statement.id) ? Color.accentColor : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(statement.propertyLabel)
                        .font(.body)
                    Text(statement.valueLabel)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(statement.propertyId)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func toggle(_ id: String) {
        if selection.contains(id) {
            selection.remove(id)
        } else {
            selection.insert(id)
        }
    }

    private func load() async {
        guard let entityId = entity.id else {
            statusMessage = "This entity has no id yet — save it before enriching."
            return
        }
        isLoading = true
        statusMessage = nil
        defer { isLoading = false }
        do {
            let fetched = try await entityStore.fetchWikidataStatements(entityId: entityId)
            preview = fetched
            if fetched.statements.isEmpty {
                statusMessage = "No statements found on Wikidata \(fetched.qid)."
            }
        } catch {
            statusMessage = "Couldn't load Wikidata statements: \(error.localizedDescription)"
        }
    }

    private func importSelected() async {
        guard let entityId = entity.id, let preview, !preview.qid.isEmpty else { return }
        let rows = preview.statements.filter { selection.contains($0.id) }
        guard !rows.isEmpty else { return }
        isImporting = true
        statusMessage = nil
        defer { isImporting = false }
        do {
            let count = try await entityStore.importWikidataStatements(
                entityId: entityId, qid: preview.qid, rows: rows
            )
            statusMessage = "Imported \(count) Wikidata-sourced claim\(count == 1 ? "" : "s")."
            selection.removeAll()
        } catch {
            statusMessage = "Import failed: \(error.localizedDescription)"
        }
    }
}
