import FicheroAPIClient
import SwiftUI

// MARK: - Curation Audit

extension EntityDetailView {
    /// Curation history surfaced from /api/kg/entity-curation/audit.
    /// Only renders when there's a history — keeps the panel tight for
    /// the 95% case where the entity hasn't been merged/split yet.
    @ViewBuilder
    var auditSection: some View {
        if isLoadingAudits {
            HStack {
                ProgressView().scaleEffect(0.7)
                Text("Loading curation history…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal)
        } else if !audits.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Curation History")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                ForEach(audits, id: \.id) { audit in
                    auditRow(audit)
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    func auditRow(_ audit: Components.Schemas.EntityAuditResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: auditIcon(audit.operationType))
                .foregroundStyle(auditTint(audit.operationType))
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(auditLabel(audit))
                    .font(.caption)
                Text(audit.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Text(audit.createdBy)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    func auditIcon(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> String {
        switch mergeOp {
        case .merge: return "arrow.triangle.merge"
        case .split: return "arrow.triangle.branch"
        case .undoMerge, .undoSplit: return "arrow.uturn.backward.circle"
        }
    }

    func auditTint(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> Color {
        switch mergeOp {
        case .merge: return .blue
        case .split: return .orange
        case .undoMerge, .undoSplit: return .gray
        }
    }

    func auditLabel(_ audit: Components.Schemas.EntityAuditResponse) -> String {
        switch audit.operationType {
        case .merge:
            return "Absorbed \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .split:
            return "Split off \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .undoMerge:
            return "Undid earlier merge"
        case .undoSplit:
            return "Undid earlier split"
        }
    }

    func loadAudits() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoadingAudits = true
        defer { isLoadingAudits = false }
        do {
            audits = try await library.entityService.listEntityAudits(entityId: entity.id, limit: 25)
        } catch {
            audits = []
        }
    }
}
