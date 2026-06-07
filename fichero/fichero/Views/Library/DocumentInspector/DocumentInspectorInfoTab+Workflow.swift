import FicheroAPIClient
import SwiftUI

// MARK: - WorkflowProvenancePanel (#1434)

/// Shows which workflow runs touched this document, backed by
/// `GET /api/documents/{id}/workflow-runs`. Lets the user see
/// which AI pipeline produced the document's entities and artifacts.
struct WorkflowProvenancePanel: View {
    let documentId: String

    @State private var runs: [Components.Schemas.WorkflowRunProvenanceResponse] = []
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if isLoading && runs.isEmpty && loadError == nil {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.6)
                    Text("Loading…").font(.caption).foregroundStyle(.secondary)
                }
            } else if let err = loadError {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.caption).foregroundStyle(.orange)
                    Text(err)
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                    Button("Retry") { Task { await load() } }
                        .font(.caption2).buttonStyle(.borderless)
                }
            } else if runs.isEmpty {
                Text("No workflow runs recorded yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                LazyVStack(alignment: .leading, spacing: 6) {
                    ForEach(runs, id: \.workflowId) { run in
                        provenanceRow(run)
                    }
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    @ViewBuilder
    private func provenanceRow(_ run: Components.Schemas.WorkflowRunProvenanceResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "gearshape.2")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(run.workflowName ?? run.workflowId)
                    .font(.caption)
                    .lineLimit(1)
                    .truncationMode(.middle)
                HStack(spacing: 4) {
                    if let model = run.model, !model.isEmpty {
                        Text(model)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                    }
                    if let started = run.startedAt, !started.isEmpty {
                        Text(relativeDate(started))
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func relativeDate(_ iso: String) -> String {
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = fmt.date(from: iso) else { return iso }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: date, relativeTo: Date())
    }

    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            runs = try await library.entityService.listDocumentWorkflowRuns(documentId: documentId)
        } catch {
            loadError = error.localizedDescription
        }
    }
}
