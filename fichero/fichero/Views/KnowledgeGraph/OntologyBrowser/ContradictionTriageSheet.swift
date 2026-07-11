import FicheroAPIClient
import SwiftUI

struct ContradictionTriageSheet: View {
    let entity: Components.Schemas.KnowledgeEntity
    let claims: [Components.Schemas.KnowledgeClaim]

    @Environment(\.dismiss) private var dismiss
    @Environment(ClaimStore.self) private var claimStore
    @State private var pairs: [Pair] = []
    @State private var isLoading = false
    @State private var selectedGroupId: String?
    @State private var selectedPairId: String?
    @State private var statusMessage: String?
    @State private var updatingIds: Set<String> = []

    struct Pair: Identifiable {
        let id: String
        let base: Components.Schemas.KnowledgeClaim
        let evidence: Components.Schemas.ContradictionEvidence
        let groupId: String
        let groupTitle: String
    }

    /// One contradiction group (keyed by `groupId`) with its display title and
    /// the pairs it contains.
    struct PairGroup: Identifiable {
        let id: String
        let title: String
        let pairs: [Pair]
    }

    private var grouped: [PairGroup] {
        let map = Dictionary(grouping: pairs, by: \.groupId)
        return map.keys.sorted().map { id in
            let items = (map[id] ?? []).sorted { ($0.evidence.linkQuality) > ($1.evidence.linkQuality) }
            return PairGroup(id: id, title: items.first?.groupTitle ?? id, pairs: items)
        }
    }

    private var currentPairs: [Pair] {
        if let selectedGroupId {
            return grouped.first(where: { $0.id == selectedGroupId })?.pairs ?? []
        }
        return grouped.first?.pairs ?? []
    }

    private var currentPair: Pair? {
        if let selectedPairId {
            return currentPairs.first(where: { $0.id == selectedPairId })
        }
        return currentPairs.first
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Contradiction Triage")
                    .font(.headline)
                Spacer()
                Button("Close") { dismiss() }
            }
            .padding(.bottom, 10)

            if let statusMessage {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.bottom, 8)
            }

            if isLoading {
                Spacer()
                ProgressView("Loading contradiction sets…")
                Spacer()
            } else if pairs.isEmpty {
                Spacer()
                Text("No contradiction sets found for this entity.")
                    .foregroundStyle(.secondary)
                Spacer()
            } else {
                HStack(spacing: 12) {
                    groupsPane
                    Divider()
                    pairListPane
                    Divider()
                    detailPane
                }
            }
        }
        .task(id: entity.id) { await load() }
    }

    private var groupsPane: some View {
        List(grouped, id: \.id, selection: $selectedGroupId) { group in
            VStack(alignment: .leading, spacing: 2) {
                Text(group.title)
                    .font(.subheadline)
                Text("\(group.pairs.count) contradiction\(group.pairs.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .tag(group.id)
        }
        .frame(minWidth: 220, maxWidth: 280)
    }

    private var pairListPane: some View {
        List(currentPairs, id: \.id, selection: $selectedPairId) { pair in
            VStack(alignment: .leading, spacing: 4) {
                Text(pair.base.text)
                    .font(.caption)
                    .lineLimit(2)
                Text(pair.evidence.contradictingText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            .tag(pair.id)
        }
        .frame(minWidth: 280, maxWidth: 360)
    }

    @ViewBuilder
    private var detailPane: some View {
        if let pair = currentPair {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(pair.groupTitle)
                        .font(.subheadline.weight(.semibold))

                    HStack(alignment: .top, spacing: 12) {
                        claimPanel(title: "Claim A", claimText: pair.base.text, claim: pair.base)
                        claimPanel(
                            title: "Claim B",
                            claimText: pair.evidence.contradictingText,
                            claim: nil,
                            sourceCount: pair.evidence.sourceDocuments.count
                        )
                    }

                    if let evidenceText = pair.evidence.evidence, !evidenceText.isEmpty {
                        Text("Link evidence: \(evidenceText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Text(String(format: "Link quality: %.2f", pair.evidence.linkQuality))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        } else {
            Text("Select a contradiction pair.")
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func claimPanel(
        title: String,
        claimText: String,
        claim: Components.Schemas.KnowledgeClaim?,
        sourceCount: Int = 0
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.caption.weight(.semibold))
            Text(claimText)
                .font(.body)
                .textSelection(.enabled)
            if let claim {
                Text("Predicate: \((claim.predicateVerb ?? "unknown").trimmingCharacters(in: .whitespacesAndNewlines))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Time: \(timeWindow(for: claim))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if sourceCount > 0 {
                Text("Provenance sources: \(sourceCount)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let claim, let claimId = claim.id {
                HStack(spacing: 8) {
                    triageButton("Shortlist", .shortlisted, claimId: claimId)
                    triageButton("Curate", .curated, claimId: claimId)
                    triageButton("Reject", .rejected, claimId: claimId)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func triageButton(
        _ title: String,
        _ state: Components.Schemas.ClaimCurationState,
        claimId: String
    ) -> some View {
        Button(title) {
            Task { await setCuration(claimId: claimId, state: state) }
        }
        .buttonStyle(.bordered)
        .disabled(updatingIds.contains(claimId))
    }

    private func timeWindow(for claim: Components.Schemas.KnowledgeClaim) -> String {
        let start = claim.timeStart?.trimmingCharacters(in: .whitespacesAndNewlines)
        let end = claim.timeEnd?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let start, !start.isEmpty, let end, !end.isEmpty {
            return "\(start) → \(end)"
        }
        if let start, !start.isEmpty { return start }
        if let end, !end.isEmpty { return end }
        return claim.sourcePageLabel ?? "unspecified"
    }

    private func groupKey(for claim: Components.Schemas.KnowledgeClaim) -> (String, String) {
        let predicate = (claim.predicateVerb ?? "unknown predicate")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let window = timeWindow(for: claim).lowercased()
        let id = "\(entity.id ?? entity.canonicalName)|\(predicate)|\(window)"
        let title = "\(predicate) • \(window)"
        return (id, title)
    }

    private func setCuration(claimId: String, state: Components.Schemas.ClaimCurationState) async {
        updatingIds.insert(claimId)
        defer { updatingIds.remove(claimId) }
        do {
            _ = try await claimStore.patch(claimId: claimId, curationState: state)
            statusMessage = "Saved: \(claimId) → \(state.rawValue)"
            // The backend emits `claim.updated`; the change-stream fans the
            // refresh to bound claim surfaces, so no NotificationCenter (#1862).
        } catch {
            statusMessage = "Failed to save curation decision"
        }
    }

    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        isLoading = true
        defer { isLoading = false }

        var loaded: [Pair] = []
        await withTaskGroup(of: [Pair].self) { group in
            for claim in claims {
                guard let claimId = claim.id else { continue }
                let key = groupKey(for: claim)
                group.addTask {
                    do {
                        let contradictions = try await library.entityService.contradictions(claimId: claimId)
                        return contradictions.map { contradiction in
                            Pair(
                                id: "\(claimId):\(contradiction.contradictingClaimId)",
                                base: claim,
                                evidence: contradiction,
                                groupId: key.0,
                                groupTitle: key.1
                            )
                        }
                    } catch {
                        return []
                    }
                }
            }
            for await part in group {
                loaded.append(contentsOf: part)
            }
        }

        pairs = loaded.sorted { $0.groupTitle < $1.groupTitle }
        if selectedGroupId == nil { selectedGroupId = grouped.first?.id }
        if selectedPairId == nil { selectedPairId = currentPairs.first?.id }
    }
}
