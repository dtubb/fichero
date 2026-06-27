import SwiftUI

/// A document page with a representation picker over a switchable canvas (#2264).
///
/// Ties the three #2264 pieces together: ``RepresentationStore`` derives the
/// available kinds from `artifacts`, ``RepresentationPicker`` switches between
/// them, and ``DocumentCanvas`` renders the chosen one. The host (reader / preview)
/// passes the document id and its already-loaded artifacts (from `ArtifactStore`,
/// the one endpoint accessor) — this view never fetches.
///
/// Today it renders `.image` and `.markdown`; the other kinds the store may list
/// (HTML/SVG/table/map/globe) fall through to an honest "not yet shown here"
/// placeholder rather than a blank or a fake. See ``Representation`` for the plan.
struct RepresentationView: View {
    let documentId: String
    let artifacts: [Artifact]

    @State private var store = RepresentationStore()

    var body: some View {
        VStack(spacing: 0) {
            if store.available.count > 1 {
                HStack {
                    RepresentationPicker(store: store)
                    Spacer()
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                Divider()
            }
            canvas
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .onAppear { store.update(documentId: documentId, artifacts: artifacts) }
        .onChange(of: documentId) { store.update(documentId: documentId, artifacts: artifacts) }
        .onChange(of: artifacts) { store.update(documentId: documentId, artifacts: artifacts) }
    }

    @ViewBuilder
    private var canvas: some View {
        switch store.selection {
        case .image:
            DocumentCanvas(content: .imageStorageDisplay(documentId: documentId))
        case .markdown:
            DocumentCanvas(content: .markdown(text: markdownText))
        default:
            ContentUnavailableView(
                store.selection.title,
                systemImage: store.selection.systemImage,
                description: Text("This representation isn't shown here yet.")
            )
        }
    }

    /// The most recent conversion/transcription artifact's text, or a hint.
    private var markdownText: String {
        let candidates = artifacts.filter {
            Representation.from(artifactType: $0.artifactType) == .markdown
        }
        let latest = candidates.max { ($0.version) < ($1.version) }
        return latest?.content ?? "_No Markdown conversion yet._"
    }
}
