import FicheroAPIClient
import SwiftUI

struct ClaimReviewQueueSheet: View {
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]

    @Environment(\.dismiss) private var dismiss
    @Environment(ClaimStore.self) private var claimStore
    @State private var personFilter = ""
    @State private var topicFilter = ""
    @State private var questionFilter = ""
    @State private var selectedIds: Set<String> = []
    @State private var updatingIds: Set<String> = []
    @State private var statusMessage: String?

    private var filteredClaims: [Components.Schemas.KnowledgeClaim] {
        claims.filter { claim in
            let personOK: Bool
            if personFilter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                personOK = true
            } else {
                personOK = (claim.subjectCanonical ?? "")
                    .localizedCaseInsensitiveContains(personFilter)
            }

            let topicOK: Bool
            if topicFilter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                topicOK = true
            } else {
                let target = "\(claim.objectPhrase ?? "") \(claim.predicateVerb ?? "")"
                topicOK = target.localizedCaseInsensitiveContains(topicFilter)
            }

            let questionOK: Bool
            if questionFilter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                questionOK = true
            } else {
                questionOK = claim.text.localizedCaseInsensitiveContains(questionFilter)
            }

            return personOK && topicOK && questionOK
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Claim Review Queue")
                    .font(.headline)
                Spacer()
                Button("Close") { dismiss() }
            }
            .padding(.bottom, 10)

            filterBar
            batchActions

            if let statusMessage {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.bottom, 6)
            }

            if filteredClaims.isEmpty {
                Spacer()
                Text("No claims match the current filters.")
                    .foregroundStyle(.secondary)
                Spacer()
            } else {
                List(filteredClaims, id: \.id) { claim in
                    claimRow(claim)
                }
            }
        }
    }

    private var filterBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Filters")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                TextField("Person", text: $personFilter)
                TextField("Topic", text: $topicFilter)
                TextField("Question", text: $questionFilter)
            }
            .textFieldStyle(.roundedBorder)
        }
        .padding(.bottom, 10)
    }

    private var batchActions: some View {
        HStack(spacing: 8) {
            Button("Select All") {
                selectedIds = Set(filteredClaims.compactMap(\.id))
            }
            .buttonStyle(.bordered)

            Button("Clear") { selectedIds.removeAll() }
                .buttonStyle(.bordered)

            Divider()
                .frame(height: 16)

            batchButton("Shortlist Selected", .shortlisted)
            batchButton("Curate Selected", .curated)
            batchButton("Reject Selected", .rejected)

            Spacer()
            Text("\(selectedIds.count) selected")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(.bottom, 10)
    }

    @ViewBuilder
    private func claimRow(_ claim: Components.Schemas.KnowledgeClaim) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Toggle(
                "",
                isOn: Binding(
                    get: { claim.id.map { selectedIds.contains($0) } ?? false },
                    set: { isOn in
                        guard let id = claim.id else { return }
                        if isOn { selectedIds.insert(id) } else { selectedIds.remove(id) }
                    }
                )
            )
            #if os(macOS)
            .toggleStyle(.checkbox)
            #endif
            .labelsHidden()
            .frame(width: 20)

            VStack(alignment: .leading, spacing: 4) {
                Text(claim.text)
                    .font(.subheadline)
                    .lineLimit(2)
                HStack(spacing: 8) {
                    Text((claim.subjectCanonical ?? "unknown").trimmingCharacters(in: .whitespacesAndNewlines))
                    Text((claim.predicateVerb ?? "predicate?").trimmingCharacters(in: .whitespacesAndNewlines))
                    Text((claim.objectPhrase ?? "object?").trimmingCharacters(in: .whitespacesAndNewlines))
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }

            Spacer()

            HStack(spacing: 6) {
                singleButton("Shortlist", claim: claim, state: .shortlisted)
                singleButton("Curate", claim: claim, state: .curated)
                singleButton("Reject", claim: claim, state: .rejected)
            }
        }
        .padding(.vertical, 4)
    }

    private func batchButton(
        _ title: String,
        _ state: Components.Schemas.ClaimCurationState
    ) -> some View {
        Button(title) {
            Task { await updateBatch(state: state) }
        }
        .buttonStyle(.borderedProminent)
        .disabled(selectedIds.isEmpty)
    }

    private func singleButton(
        _ title: String,
        claim: Components.Schemas.KnowledgeClaim,
        state: Components.Schemas.ClaimCurationState
    ) -> some View {
        Button(title) {
            Task { await updateSingle(claim: claim, state: state) }
        }
        .buttonStyle(.bordered)
        .disabled(claim.id.map { updatingIds.contains($0) } ?? true)
    }

    private func updateSingle(
        claim: Components.Schemas.KnowledgeClaim,
        state: Components.Schemas.ClaimCurationState
    ) async {
        guard let claimId = claim.id else { return }
        updatingIds.insert(claimId)
        defer { updatingIds.remove(claimId) }
        do {
            // Through the store (#1848). The old call went straight to
            // `entityService`, so this sheet edited a list that did not know it
            // had changed: the comment below promised the change stream would
            // fan the refresh, but nothing bumped the store's own scope, and a
            // sheet dismissed before the stream arrived left the surface behind
            // it stale.
            _ = try await claimStore.patch(claimId: claimId, curationState: state)
            statusMessage = "Updated \(claimId) → \(state.rawValue)"
            // Backend emits `claim.updated`; change-stream fans the refresh (#1862).
        } catch {
            statusMessage = "Failed to update \(claimId)"
        }
    }

    private func updateBatch(state: Components.Schemas.ClaimCurationState) async {
        let claimIds = Array(selectedIds)
        guard !claimIds.isEmpty else { return }
        var successCount = 0
        for claimId in claimIds {
            updatingIds.insert(claimId)
            defer { updatingIds.remove(claimId) }
            do {
                _ = try await claimStore.patch(claimId: claimId, curationState: state)
                successCount += 1
                // Backend emits `claim.updated`; change-stream fans refresh (#1862).
            } catch {
                continue
            }
        }
        statusMessage = "Batch update: \(successCount)/\(claimIds.count) → \(state.rawValue)"
    }
}
