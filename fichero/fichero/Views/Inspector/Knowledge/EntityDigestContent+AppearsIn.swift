import FicheroAPIClient
import SwiftUI

// Split out of EntityDigestView.swift (#4896 lint follow-up: type_body_length
// 365/250, file_length 784/400) — a MOVE only, no behaviour change. See the
// doc comment on `EntityDigestContent` in EntityDigestView.swift for the
// access-level rule this split follows.
extension EntityDigestContent {
    var appearsInSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(appearsIn.isEmpty ? "Appears In" : "Appears In (\(appearsIn.count))")
                .font(.headline)
                .padding(.bottom, 4)

            if appearsIn.isEmpty {
                Text(isLoading ? " " : "No source documents recorded.")
                    .foregroundStyle(.secondary)
                    .italic()
            } else {
                // Real rows: select to reveal in the reading surface via the
                // SAME source cursor claims use; drag out as plain text ids
                // for now (full library-drag payload is queued).
                List(selection: $selectedAppearsRowId) {
                    ForEach(appearsIn) { doc in
                        HStack(spacing: 8) {
                            Image(systemName: doc.docType == .folder ? "folder" : "doc.text.image")
                                .foregroundStyle(.secondary)
                            // Not `doc.name` (#4416): a page child's name is
                            // the engine's upload temp file — compose the
                            // display title like every other surface.
                            Text(docName(for: doc.id))
                                .lineLimit(1)
                            Spacer()
                        }
                        .tag(doc.id)
                        .draggable(doc.id)
                    }
                }
                .listStyle(.inset)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 80, maxHeight: 280)
                .onChange(of: selectedAppearsRowId) { _, newSelection in
                    guard let newSelection else { return }
                    // #4834: a document pick, not a statement click — `.reader` stated explicitly.
                    claimSourceNavigationState?.request(
                        ClaimSourceNavigationRequest(documentId: newSelection, destination: .reader)
                    )
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    func loadAppearsIn() async {
        let ids = entity.sourceDocumentIds ?? []
        guard !ids.isEmpty, let documentService else {
            appearsIn = []
            return
        }
        appearsIn = (try? await documentService.getDocuments(ids: ids)) ?? []
    }
}
