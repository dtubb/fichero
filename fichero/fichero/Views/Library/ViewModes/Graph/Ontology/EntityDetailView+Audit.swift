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
                HStack {
                    Text("Curation History")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Spacer()
                    if let auditStatusMessage {
                        Text(auditStatusMessage)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                ForEach(audits, id: \.id) { audit in
                    auditRow(audit)
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial)
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
            if canUndo(audit) {
                Button {
                    Task { await undoAudit(audit.id) }
                } label: {
                    if undoingAuditId == audit.id {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Undo")
                            .font(.caption2)
                    }
                }
                .buttonStyle(.borderless)
                .disabled(undoingAuditId != nil)
            }
        }
        .padding(.vertical, 2)
    }

    private func canUndo(_ audit: Components.Schemas.EntityAuditResponse) -> Bool {
        switch audit.operationType {
        case .merge, .split, .authorityLink:
            return audit.reversalId == audit.id
        case .undoMerge, .undoSplit:
            return false
        }
    }

    func auditIcon(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> String {
        switch mergeOp {
        case .merge: return "arrow.triangle.merge"
        case .split: return "arrow.triangle.branch"
        case .authorityLink: return "link"
        case .undoMerge, .undoSplit: return "arrow.uturn.backward.circle"
        }
    }

    func auditTint(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> Color {
        switch mergeOp {
        case .merge: return .blue
        case .split: return .orange
        case .authorityLink: return .purple
        case .undoMerge, .undoSplit: return .gray
        }
    }

    func auditLabel(_ audit: Components.Schemas.EntityAuditResponse) -> String {
        switch audit.operationType {
        case .merge:
            return "Absorbed \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .split:
            return "Split off \(audit.sourceEntityIds.count) entity\(audit.sourceEntityIds.count == 1 ? "" : "s")"
        case .authorityLink:
            return "Linked to an authority record"
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

    func undoAudit(_ auditId: String) async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        undoingAuditId = auditId
        defer { undoingAuditId = nil }
        do {
            _ = try await library.entityService.undoEntityAudit(auditId)
            auditStatusMessage = "Undo complete"
            await loadAudits()
        } catch {
            auditStatusMessage = "Undo failed"
        }
    }
}

// MARK: - Possible Duplicates / Related Entities (#3317)

/// A candidate duplicate/variant of the inspected entity, surfaced by embedding
/// similarity (catches spelling/accent/cross-script variants that structural
/// co-occurrence misses).
struct DuplicateCandidate: Identifiable, Hashable {
    let id: String
    let name: String
    let entityType: String?
    /// Similarity confidence in [0, 1].
    let score: Double
}

extension EntityDetailView {
    /// Review-only surface: lists likely duplicate entities with a confidence
    /// indicator and a one-click, audited (undoable) merge in either direction.
    /// The system never merges automatically (#3317).
    @ViewBuilder
    var possibleDuplicatesSection: some View {
        if isLoadingDuplicates || !duplicateCandidates.isEmpty || duplicateActionMessage != nil {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Label("Possible Duplicates", systemImage: "square.on.square")
                        .font(.headline)
                    if isLoadingDuplicates {
                        ProgressView().controlSize(.small)
                    }
                    Spacer()
                }
                if let message = duplicateActionMessage {
                    Text(message).font(.caption).foregroundStyle(.secondary)
                }
                if duplicateCandidates.isEmpty && !isLoadingDuplicates {
                    Text("No likely duplicates found.")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    ForEach(duplicateCandidates) { candidate in
                        duplicateRow(candidate)
                    }
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    private func duplicateRow(_ candidate: DuplicateCandidate) -> some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(candidate.name).font(.body).lineLimit(1)
                if let type = candidate.entityType {
                    Text(type.capitalized).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Text("\(Int((candidate.score * 100).rounded()))%")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(candidate.score >= 0.85 ? Color.orange : .secondary)
                .help("Similarity confidence")
            Menu {
                // One click per direction — the survivor is the user's choice
                // (the #2499 destination pick, for a pair).
                Button("Keep \"\(displayName)\"") { mergeDuplicate(candidate, keepThis: true) }
                Button("Keep \"\(candidate.name)\"") { mergeDuplicate(candidate, keepThis: false) }
            } label: {
                Label("Merge", systemImage: "arrow.triangle.merge").font(.caption)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
        .padding(.vertical, 2)
    }

    func loadDuplicateCandidates() async {
        guard let entityId = entity.id else { return }
        isLoadingDuplicates = true
        defer { isLoadingDuplicates = false }
        do {
            let data = try await entityService.searchEntitiesSemantic(
                query: entity.canonicalName,
                entityType: entity.entityType?.rawValue,
                limit: 12
            )
            duplicateCandidates = Self.parseDuplicateCandidates(data, excluding: entityId)
        } catch {
            duplicateCandidates = []
        }
    }

    /// Parse the `/semantic` response into candidates, dropping the entity
    /// itself and weak matches. Exposed for tests.
    static func parseDuplicateCandidates(_ data: Data, excluding entityId: String) -> [DuplicateCandidate] {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = obj["items"] as? [[String: Any]] else { return [] }
        return items.compactMap { item -> DuplicateCandidate? in
            guard let id = item["id"] as? String, id != entityId else { return nil }
            let name = (item["canonical_name"] as? String) ?? (item["name"] as? String) ?? "Unknown"
            let type = item["entity_type"] as? String
            let score = (item["similarity_score"] as? Double) ?? (item["score"] as? Double) ?? 0
            guard score >= 0.4 else { return nil }
            return DuplicateCandidate(id: id, name: name, entityType: type, score: score)
        }
    }

    func mergeDuplicate(_ candidate: DuplicateCandidate, keepThis: Bool) {
        guard let entityId = entity.id else { return }
        let survivorId = keepThis ? entityId : candidate.id
        let absorbedId = keepThis ? candidate.id : entityId
        Task {
            do {
                try await entityStore.merge(absorbedIds: [absorbedId], into: survivorId)
                duplicateActionMessage = keepThis
                    ? "Merged \"\(candidate.name)\" into \"\(displayName)\"."
                    : "Merged \"\(displayName)\" into \"\(candidate.name)\"."
                await loadDuplicateCandidates()
            } catch {
                duplicateActionMessage = "Couldn't merge: \(error.localizedDescription)"
            }
        }
    }
}
