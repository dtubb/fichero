import FicheroAPIClient
import SwiftUI

/// A folder's Inspector: the documents Find the Documents proposed and a person has yet to answer
/// (#5550, `finddocs.accept-makes-groups`), each with its pages, kind, confidence and reasons, and
/// Accept, Reject and Accept All Above. Shown only while something is waiting.
struct FoundDocumentsInspectorSection: View {
    let document: Document

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?

    private var store: FoundDocumentsStore? {
        documentStore.flatMap { libraryManager?.library(owningService: $0)?.foundDocumentsStore }
    }

    var body: some View {
        if document.docType == .folder, let store {
            let folderId = document.id
            FoundDocumentsSection(
                waiting: store.waiting[folderId] ?? [],
                busy: store.busy,
                errorMessage: store.errorMessage,
                accept: { item in await change { await store.accept(item, folderId: folderId) } },
                reject: { item in await store.reject(item, folderId: folderId) },
                acceptAll: { threshold in await change { await store.acceptAll(above: threshold, folderId: folderId) } }
            )
            .task(id: folderId) { await store.load(folderId: folderId) }
        }
    }

    /// An accept makes group nodes, so the folder's contents are read again after it.
    private func change(_ work: () async -> Void) async {
        await work()
        await documentStore?.refresh()
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
                        document: item.document,
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
    let document: Components.Schemas.ProposedDocument
    let busy: Bool
    let accept: () -> Void
    let reject: () -> Void

    private var pages: String {
        let first = document.firstPosition + 1, last = document.lastPosition + 1
        return first == last ? "Page \(first)" : "Pages \(first)–\(last)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(document.name).font(.body).lineLimit(2)
                Spacer()
                Text(document.confidence.formatted(.percent.precision(.fractionLength(0))))
                    .font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }
            Text([pages, document.kind].compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(.secondary)
            if let reasons = document.reasons, !reasons.isEmpty {
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
