import FicheroAPIClient
import SwiftUI

// MARK: - Speaker Comparison View

struct SpeakerComparisonView: View {
    let claims: [Components.Schemas.KnowledgeClaim]

    /// Groups claims by speaker
    private var claimsBySpeaker: [(speaker: String, claims: [Components.Schemas.KnowledgeClaim])] {
        var speakerGroups: [String: [Components.Schemas.KnowledgeClaim]] = [:]

        for claim in claims {
            let speaker = claim.speakerName ?? "Unknown Speaker"
            if speakerGroups[speaker] == nil {
                speakerGroups[speaker] = []
            }
            speakerGroups[speaker]?.append(claim)
        }

        return speakerGroups.map { (speaker: $0.key, claims: $0.value) }.sorted { $0.speaker < $1.speaker }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Title and badge
                HStack {
                    Text("Multi-Speaker Claims")
                        .font(.headline)
                    Spacer()
                    if claimsBySpeaker.count > 1 {
                        Text("\(claimsBySpeaker.count) voices ›")
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.blue.opacity(0.1))
                            .foregroundColor(.blue)
                            .cornerRadius(6)
                    }
                }
                .padding(.horizontal)

                // Speaker comparison cards
                ForEach(claimsBySpeaker, id: \.speaker) { speakerGroup in
                    SpeakerGroupView(
                        speaker: speakerGroup.speaker,
                        claims: speakerGroup.claims
                    )
                }
            }
            .padding(.vertical)
        }
    }
} // SpeakerComparisonView

// MARK: - Speaker Group View

struct SpeakerGroupView: View {
    let speaker: String
    let claims: [Components.Schemas.KnowledgeClaim]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(speaker)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(claims.count) claims")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            // Display claims with speaker info
            ForEach(claims, id: \.id) { claim in
                ClaimSummaryCard(claim: claim)
            }
        }
        .padding(12)
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(8)
    }
}
