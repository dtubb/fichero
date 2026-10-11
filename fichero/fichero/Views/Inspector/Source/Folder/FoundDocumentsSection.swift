import FicheroAPIClient
import SwiftUI

/// A folder's Inspector: the documents Find the Documents proposed and a person has yet to answer
/// (#5550, `finddocs.accept-makes-groups`), each with its pages, kind, confidence and reasons, and
/// Accept, Reject and Accept All Above. Shown only while something is waiting.
struct FoundDocumentsInspectorSection: View {
    let document: Document

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    private var library: LibraryManager.LibraryReference? {
        documentStore.flatMap { libraryManager?.library(owningService: $0) }
    }

    var body: some View {
        if document.docType == .folder, let library {
            let store = library.foundDocumentsStore
            let folderId = document.id
            // An accept makes group nodes, so the folder's contents are read again after it and after its undo.
            let answering = FoundDocumentsStore.Answering(
                actions: library.actionsService, steps: windowSteps, afterChange: { await documentStore?.refresh() }
            )
            FoundDocumentsSection(
                waiting: store.waiting[folderId] ?? [],
                busy: store.busy,
                errorMessage: store.errorMessage,
                accept: { item in await store.accept([item], folderId: folderId, via: answering) },
                reject: { item in await store.reject([item], folderId: folderId, via: answering) },
                acceptAll: { threshold in await store.acceptAll(above: threshold, folderId: folderId, via: answering) }
            )
            .task(id: folderId) { await store.load(folderId: folderId) }
        }
    }
}

/// The section's body, given what the store holds.
struct FoundDocumentsSection: View {
    let waiting: [FoundDocumentsStore.Waiting]
    let busy: Bool
    let errorMessage: String?
    let accept: (FoundDocumentsStore.Waiting) async -> Void
    let reject: (FoundDocumentsStore.Waiting) async -> Void
    let acceptAll: (Double) async -> Void

    var body: some View {
        if !waiting.isEmpty || errorMessage != nil {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Proposed documents").font(.headline)
                    Spacer()
                    Menu("Accept All") {
                        ForEach(FoundDocumentsStore.thresholds, id: \.self) { threshold in
                            Button("At least \(threshold.formatted(.percent)) sure") {
                                Task { await acceptAll(threshold) }
                            }
                        }
                    }
                    .fixedSize()
                    .disabled(busy || waiting.isEmpty)
                }
                ForEach(waiting) { item in
                    FoundDocumentRow(
                        proposal: item.document,
                        busy: busy,
                        accept: { Task { await accept(item) } },
                        reject: { Task { await reject(item) } }
                    )
                }
                if let errorMessage {
                    Text(errorMessage).font(.caption).foregroundStyle(.secondary)
                }
            }
            .accessibilityIdentifier("inspector.foundDocuments")
        }
    }
}

private struct FoundDocumentRow: View {
    /// A document the engine proposes (#5550): its name is the proposed title, never a stored `Document.name`.
    let proposal: Components.Schemas.ProposedDocument
    let busy: Bool
    let accept: () -> Void
    let reject: () -> Void

    private var pages: String {
        let first = proposal.firstPosition + 1, last = proposal.lastPosition + 1
        return first == last ? "Page \(first)" : "Pages \(first)–\(last)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(proposal.name).font(.body).lineLimit(2)
                Spacer()
                Text(proposal.confidence.formatted(.percent.precision(.fractionLength(0))))
                    .font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
            Text([pages, proposal.kind].compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary)
            if let reasons = proposal.reasons, !reasons.isEmpty {
                Text(reasons.joined(separator: "; ")).font(.caption).foregroundStyle(.secondary).lineLimit(3)
            }
            HStack {
                Button("Accept", action: accept)
                Button("Reject", action: reject)
            }
            .controlSize(.small)
            .disabled(busy)
        }
    }
}

#Preview("Proposed documents") {
    FoundDocumentsSection(
        waiting: [
            .init(proposalId: "p1", document: .init(
                index: 0, name: "Sentencia, 1924", pageIds: ["a", "b", "c"], firstPosition: 0, lastPosition: 2,
                kind: "Sentencia", confidence: 0.82, reasons: ["VISTOS at the head of page 1", "folio numbers run on"]
            )),
            .init(proposalId: "p1", document: .init(
                index: 1, name: "Carta", pageIds: ["d"], firstPosition: 3, lastPosition: 3,
                kind: "Carta", confidence: 0.64, reasons: ["a salutation opens the page"]
            )),
        ],
        busy: false,
        errorMessage: nil,
        accept: { _ in }, reject: { _ in }, acceptAll: { _ in }
    )
    .padding()
    .frame(width: 320)
}
