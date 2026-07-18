import FicheroAPIClient
import SwiftUI

// MARK: - KG Curation History (#1434)

/// Collapsible "Curation History" panel at the bottom of the KG tab.
/// Shows recent entity merge/split audit records from
/// `/api/kg/entity-curation/audit` with per-row Undo buttons.
/// Only rendered when there are audit records — keeps the panel tight
/// for the common case where no curation has happened.
struct KGCurationHistorySection: View {
    let entityService: EntityService

    @State private var audits: [Components.Schemas.EntityAuditResponse] = []
    @State private var isLoading = false
    @State private var undoingId: String?
    @State private var statusMessage: String?
    @State private var isExpanded = false
    @State private var loadTrigger = 0

    var body: some View {
        if !audits.isEmpty || isLoading {
            DisclosureGroup(
                isExpanded: $isExpanded,
                content: {
                    if isLoading {
                        HStack(spacing: 6) {
                            ProgressView().scaleEffect(0.6)
                            Text("Loading…").font(.caption).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    } else {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(audits, id: \.id) { audit in
                                auditRow(audit)
                            }
                            if let msg = statusMessage {
                                Text(msg)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .padding(.top, 2)
                            }
                        }
                    }
                },
                label: {
                    HStack(spacing: 4) {
                        Image(systemName: "clock.arrow.trianglehead.counterclockwise.rotate.90")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Curation History (\(audits.count))")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)
                    }
                }
            )
            .task(id: loadTrigger) { await load() }
        }
    }

    private func auditRow(_ audit: Components.Schemas.EntityAuditResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: auditIcon(audit.operationType))
                .foregroundStyle(auditTint(audit.operationType))
                .font(.caption)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(auditLabel(audit))
                    .font(.caption)
                Text(audit.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Spacer(minLength: 0)
            if canUndo(audit) {
                Button {
                    Task { await undo(audit.id) }
                } label: {
                    if undoingId == audit.id {
                        ProgressView().controlSize(.mini)
                    } else {
                        Text("Undo")
                            .font(.caption2)
                    }
                }
                .buttonStyle(.borderless)
                .disabled(undoingId != nil)
            }
        }
        .padding(.vertical, 2)
    }

    private func canUndo(_ audit: Components.Schemas.EntityAuditResponse) -> Bool {
        switch audit.operationType {
        case .merge, .split, .authorityLink: return audit.reversalId == nil
        case .undoMerge, .undoSplit: return false
        }
    }

    private func auditIcon(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> String {
        switch mergeOp {
        case .merge: return "arrow.triangle.merge"
        case .split: return "arrow.triangle.branch"
        case .authorityLink: return "link"
        case .undoMerge, .undoSplit: return "arrow.uturn.backward.circle"
        }
    }

    private func auditTint(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> Color {
        switch mergeOp {
        case .merge: return .blue
        case .split: return .orange
        case .authorityLink: return .purple
        case .undoMerge, .undoSplit: return .gray
        }
    }

    private func auditLabel(_ audit: Components.Schemas.EntityAuditResponse) -> String {
        switch audit.operationType {
        case .merge:
            let cnt = audit.sourceEntityIds.count
            return "Merged \(cnt) entr\(cnt == 1 ? "y" : "ies")"
        case .split:
            return "Split entity"
        case .authorityLink:
            return "Linked to an authority record"
        case .undoMerge:
            return "Undid merge"
        case .undoSplit:
            return "Undid split"
        }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        audits = (try? await entityService.listEntityAudits(limit: 20)) ?? []
    }

    private func undo(_ auditId: String) async {
        undoingId = auditId
        defer { undoingId = nil }
        do {
            _ = try await entityService.undoEntityAudit(auditId)
            statusMessage = "Undo complete"
            loadTrigger += 1
        } catch {
            statusMessage = "Undo failed"
        }
    }
}
