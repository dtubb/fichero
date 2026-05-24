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
                    speakerName: "Witness A",
                    sourceDocumentId: "doc1"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim2",
                    text: "Another testimony about the event",
                    speakerName: "Witness B",
                    sourceDocumentId: "doc1"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim3",
                    text: "Yet another perspective",
                    speakerName: "Witness A",
                    sourceDocumentId: "doc2"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim4",
                    text: "The defendant's statement",
                    speakerName: "Defendant",
                    sourceDocumentId: "doc3"
                )
            ])
            .previewDisplayName("Multi-Speaker Claims")
            
            // Preview with single speaker
            SpeakerComparisonView(claims: [
                Components.Schemas.KnowledgeClaim(
                    id: "claim1",
                    text: "A single speaker's account",
                    speakerName: "Speaker One",
                    sourceDocumentId: "doc1"
                ),
                Components.Schemas.KnowledgeClaim(
                    id: "claim2",
                    text: "Another statement",
                    speakerName: "Speaker One",
                    sourceDocumentId: "doc2"
                )
            ])
            .previewDisplayName("Single Speaker Claims")
        }
        .padding()
    }
}
#endif