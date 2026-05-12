import FicheroAPIClient
import SwiftUI

// MARK: - Claim Summary Card

struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim

    /// Expanded → fetches contradictions + evidence-chain + similar
    /// claims in parallel. Collapsed by default; this is one-of-many
    /// in a list so the panel stays tight.
    @State private var isExpanded: Bool = false
    @State private var contradictions: [Components.Schemas.ContradictionEvidence]?
    @State private var evidenceChain: Components.Schemas.EvidenceChain?
    @State private var isLoadingDetails: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                Text(claim.text)
                    .font(.caption)
                    .lineLimit(isExpanded ? nil : 2)
                    .textSelection(.enabled)
                Spacer(minLength: 0)
                Button {
                    isExpanded.toggle()
                    if isExpanded {
                        Task { await loadDetails() }
                    }
                } label: {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundStyle(.secondary)
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .help(isExpanded ? "Hide details" : "Show contradictions + evidence chain")
            }

            // Verbatim source quote the LLM lifted the claim from
            // (#892/#893). Italicised + smaller font so it reads as a
            // citation underneath the composed claim sentence. Tap to
            // run a library search for that exact text — same code
            // path as the entity lozenges (ficheroEntitySearchRequested
            // → ContentView → runToolbarSearch), with no entityType so
            // it goes through the free-text branch.
            if let excerpt = claim.sourceExcerpt?.trimmingCharacters(in: .whitespacesAndNewlines),
               !excerpt.isEmpty,
               excerpt != claim.text {
                Button {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": excerpt]
                    )
                } label: {
                    Text("“\(excerpt)”")
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help("Search the library for this quote")
            }

            HStack(spacing: 8) {
                if let claimType = claim.claimType {
                    Text(claimType.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.gray.opacity(0.2))
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }

                if let epistemicStatus = claim.epistemicStatus {
                    Text(epistemicStatus.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(statusColor.opacity(0.2))
                        .foregroundStyle(statusColor)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }

            if isExpanded {
                expandedDetailSection
            }
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .contextMenu {
            Button("Delete claim…", role: .destructive) {
                deleteClaim()
            }
        }
    }

    /// Inline detail panel — contradictions + evidence-chain summary.
    /// Lights up the post-1587a1b6 claim-analysis surface inside the
    /// existing OntologyBrowser shell so the new backend has UI today.
    @ViewBuilder
    private var expandedDetailSection: some View {
        Divider()
        if isLoadingDetails {
            HStack {
                ProgressView().scaleEffect(0.6)
                Text("Loading analysis…")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                if let cons = contradictions, !cons.isEmpty {
                    Label("\(cons.count) contradiction\(cons.count == 1 ? "" : "s")",
                          systemImage: "exclamationmark.triangle")
                        .font(.caption2)
                        .foregroundStyle(.red)
                    ForEach(Array(cons.prefix(3).enumerated()), id: \.offset) { _, contradiction in
                        Text("• \(contradiction.contradictingText)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                } else {
                    Label("No contradictions recorded", systemImage: "checkmark.seal")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let chain = evidenceChain {
                    let linkCount = chain.relatedClaims.count
                    let sourceCount = chain.sources.count
                    Label(
                        "\(sourceCount) source\(sourceCount == 1 ? "" : "s"), \(linkCount) related claim\(linkCount == 1 ? "" : "s")",
                        systemImage: "link"
                    )
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func loadDetails() async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        isLoadingDetails = true
        defer { isLoadingDetails = false }
        async let contradictionsAsync = try? library.entityService.contradictions(claimId: claimId)
        async let evidenceChainAsync = try? library.entityService.evidenceChain(claimId: claimId)
        let cons = await contradictionsAsync ?? []
        let chain = await evidenceChainAsync
        contradictions = cons
        evidenceChain = chain
    }

    fileprivate func deleteClaim() {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        Task {
            do {
                try await library.entityService.deleteClaim(claimId)
                NotificationCenter.default.post(name: .ficheroClaimDeleted, object: claimId)
            } catch {
                NotificationCenter.default.post(
                    name: .ficheroClaimDeleted,
                    object: nil,
                    userInfo: ["error": error.localizedDescription]
                )
            }
        }
    }

    private var statusColor: Color {
        guard let status = claim.epistemicStatus else { return .gray }
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}
