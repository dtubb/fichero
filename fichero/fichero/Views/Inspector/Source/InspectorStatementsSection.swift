import SwiftUI

/// The Inspector's statements (5.7, second half): the claims and mentions whose anchor names this
/// segment, each opening its claim or entity in the knowledge views (the one focus the Reader and the
/// Knowledge inspector already follow). Read-only; hidden when nothing is said about the segment.
struct InspectorStatementsSection: View {
    let segmentId: String
    let documentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(KGFocusState.self) private var kgFocusState: KGFocusState?
    @State private var answer = InspectorStatements.Answer()

    var body: some View {
        // The container always exists, so the load runs while the section has nothing to show.
        VStack(alignment: .leading, spacing: 0) {
            let rows = InspectorStatements.rows(answer)
            if !rows.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Said About This").font(.headline)
                    ForEach(rows) { row in
                        Button { open(row) } label: {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(row.title).font(.body).multilineTextAlignment(.leading)
                                Text(row.detail).font(.caption).foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                        .help(row.isClaim ? "Open this claim" : "Open this entity")
                        .accessibilityHint(row.isClaim ? "Opens the claim" : "Opens the entity")
                    }
                }
            }
        }
        .task(id: segmentId) { await reload() }
    }

    private func open(_ row: InspectorStatements.Row) {
        guard let kgFocusState else { return }
        if row.isClaim {
            kgFocusState.focusClaim(claimId: row.targetId, entityId: nil, sourceDocumentId: documentId)
        } else {
            kgFocusState.focusEntity(entityId: row.targetId, sourceDocumentId: documentId)
        }
    }

    private func reload() async {
        guard let segmentService else { return }
        answer = (try? await StatementService(client: segmentService.client).statements(segmentId: segmentId))
            ?? InspectorStatements.Answer()
    }
}
