import SwiftUI

/// Interpretation tab in the Document Inspector (#2470).
///
/// The user's own reading of the document — the **Interpretation layer** of the
/// three-layer knowledge model (Ontology = AI facts, Hermeneutic = what the
/// sources say, Interpretation = what *I* think). Kept in its own surface,
/// Notes-adjacent, and deliberately OUT of the Knowledge Graph tab so the app
/// never presents the user's interpretation as an AI-asserted fact
/// (AI-integrity north star).
///
/// A thin host: it reuses the existing `DocumentInterpretationsSection` (which
/// reads the shared `InterpretationStore`) rather than re-building the list —
/// iterate, don't replace. Wrapped in a `ScrollView` so the section gets its own
/// scroll space instead of fighting the Notes tab's List+detail layout.
struct DocumentInterpretationsTab: View {
    let document: Document

    @EnvironmentObject private var entityService: EntityServiceGenerated

    var body: some View {
        ScrollView {
            DocumentInterpretationsSection(
                documentId: document.id,
                entityService: entityService
            )
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
