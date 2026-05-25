import FicheroAPIClient
import SwiftUI

// MARK: - Preview for Speaker Comparison View

#if DEBUG
struct SpeakerComparisonView_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            // Preview with multiple speakers
            SpeakerComparisonView(claims: [
                Components.Schemas.KnowledgeClaim(
                    id: "claim1",
                    text: "The witness spoke about his experience",
                    sourceDocumentId: "doc1",
                    speakerName: "Witness A"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim2",
                    text: "Another testimony about the event",
                    sourceDocumentId: "doc1",
                    speakerName: "Witness B"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim3",
                    text: "Yet another perspective",
                    sourceDocumentId: "doc2",
                    speakerName: "Witness A"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim4",
                    text: "The defendant's statement",
                    sourceDocumentId: "doc3",
                    speakerName: "Defendant"
                )
            ])
            .previewDisplayName("Multi-Speaker Claims")

            // Preview with single speaker
            SpeakerComparisonView(claims: [
                Components.Schemas.KnowledgeClaim(
                    id: "claim1",
                    text: "A single speaker's account",
                    sourceDocumentId: "doc1",
                    speakerName: "Speaker One"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim2",
                    text: "Another statement",
                    sourceDocumentId: "doc2",
                    speakerName: "Speaker One"
                )
            ])
            .previewDisplayName("Single Speaker Claims")
        }
        .padding()
    }
}
#endif // DEBUG
