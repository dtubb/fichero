import FicheroAPIClient
import SwiftUI

// MARK: - WorkflowProvenancePanel (#1434, #2434)

/// Shows which workflow runs touched this document, backed by
/// `GET /api/documents/{id}/workflow-runs`. Lists name, relative timestamp,
/// and derived status; newest run first.
struct WorkflowProvenancePanel: View {
    let documentId: String

    @Environment(EntityService.self) private var entityService
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
                    ForEach(runs, id: \.stableId) { run in
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
            Image(systemName: run.statusIcon)
                .font(.caption2)
                .foregroundStyle(run.statusColor)
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
        // Use the canonical lenient parser: a bare .withFractionalSeconds formatter
        // REJECTS whole-second engine timestamps, which would render the raw ISO
        // string instead of a relative date (sibling of the sortNewestFirst bug, #4016).
        guard let date = parseEngineDate(iso) else { return iso }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: date, relativeTo: Date())
    }

    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let fetched = try await entityService.listDocumentWorkflowRuns(documentId: documentId)
            runs = WorkflowProvenancePanel.sortNewestFirst(fetched)
        } catch {
            loadError = Self.loadErrorMessage(for: error)
        }
    }

    // MARK: - Testable sort

    // nonisolated: pure date-sort with no main-actor state. Without this it inherits
    // @MainActor from the View type, and `.sorted`'s comparator runs on a background
    // cooperative queue → swift_task_isCurrentExecutor assertion crash (#3902 test host).
    nonisolated static func sortNewestFirst(
        _ runs: [Components.Schemas.WorkflowRunProvenanceResponse]
    ) -> [Components.Schemas.WorkflowRunProvenanceResponse] {
        // ISO8601DateFormatter with .withFractionalSeconds REJECTS whole-second
        // timestamps like "2024-06-01T00:00:00Z" — and the engine emits exactly
        // those whenever microseconds are zero (Python datetime.isoformat()). Parse
        // fractional first, then fall back to plain internet-date-time; otherwise
        // every whole-second run collapsed to .distantPast and the sort became a
        // silent no-op that preserved input order instead of newest-first (#4016).
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        func startedDate(_ value: String?) -> Date {
            guard let value else { return .distantPast }
            return fractional.date(from: value) ?? plain.date(from: value) ?? .distantPast
        }
        return runs.sorted { lhs, rhs in
            startedDate(lhs.startedAt) > startedDate(rhs.startedAt)
        }
    }

    nonisolated static func loadErrorMessage(for error: Error) -> String? {
        if case EntityService.ServiceError.unexpectedResponse(404) = error {
            return nil
        }
        return error.localizedDescription
    }
}

// MARK: - WorkflowRunProvenanceResponse helpers

private extension Components.Schemas.WorkflowRunProvenanceResponse {
    /// Stable ForEach identity — thread+batch+workflow+time avoids duplicate-key crashes
    /// when the same workflow ran multiple times on this document.
    var stableId: String {
        (threadId ?? "") + (batchId ?? "") + workflowId + (startedAt ?? "")
    }

    var statusIcon: String {
        if completedAt != nil {
            return "checkmark.circle.fill"
        }
        if startedAt != nil {
            return "clock.circle.fill"
        }
        return "circle"
    }

    var statusColor: Color {
        if completedAt != nil {
            return .green
        }
        if startedAt != nil {
            return .blue
        }
        return .secondary
    }
}
