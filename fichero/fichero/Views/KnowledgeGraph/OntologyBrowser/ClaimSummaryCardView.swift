import FicheroAPIClient
import SwiftUI

// MARK: - Claim Summary Card

struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(claim.text)
                .font(.caption)
                .lineLimit(2)
                .textSelection(.enabled)

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
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
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
