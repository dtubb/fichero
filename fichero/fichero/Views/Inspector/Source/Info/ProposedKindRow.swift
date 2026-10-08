import OSLog
import SwiftUI

/// A kind a run proposed for this node, with Accept and Reject (#5600,
/// `source.extract.kinds-proposed-as-prototypes`). Each answer is the engine's audited action; after
/// it the node is read again into the one `DocumentStore`, in place, so the Class row and this
/// proposal change where they are shown.
struct ProposedKindRow: View {
    let documentId: String
    let proposal: ProposedKind
    /// The entity service of the library that owns `documentId` (as `DocumentPrototypePicker`).
    let entityService: EntityService?
    /// Reads the node again after an answer (`DocumentStore.refreshDocumentsByIds`); nil in previews.
    var reread: ((String) async -> Void)?

    @State private var isAnswering = false
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("Proposed kind: \(proposal.label)", systemImage: "sparkles")
                .font(.callout)
            Text(proposal.byWhom)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let said = proposal.said {
                Text("“\(said)”")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
                    .textSelection(.enabled)
            }
            HStack(spacing: 8) {
                Button("Accept") { Task { await answer(accept: true) } }
                    .help("Make \(proposal.label) this node's kind; the run stays its source")
                Button("Reject") { Task { await answer(accept: false) } }
                    .help("Keep the node's kind; this kind is not proposed again")
                if isAnswering {
                    ProgressView().controlSize(.mini)
                }
            }
            .controlSize(.small)
            .disabled(isAnswering || entityService == nil)
            if let failure {
                Label(failure, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    private func answer(accept: Bool) async {
        guard let entityService else { return }
        isAnswering = true
        defer { isAnswering = false }
        do {
            if accept {
                try await entityService.acceptProposedKind(documentId: documentId)
            } else {
                try await entityService.rejectProposedKind(documentId: documentId)
            }
            failure = nil
            await reread?(documentId)
        } catch {
            if error.isCancellationError { return }
            failure = "Could not \(accept ? "accept" : "reject") the kind: \(error.localizedDescription)"
            Logger(subsystem: "app.fichero", category: "ProposedKind")
                .error("Proposed kind answer failed: \(error.localizedDescription)")
        }
    }
}

extension ProposedKind {
    /// A waiting proposal as the engine writes it, for previews.
    static let preview = ProposedKind(metadata: [
        "proposed_attributes": AnyCodable([
            "prototype": [
                "value": "letter", "label": "Letter", "state": "proposed",
                "source": ["by": "machine", "tool": "classify", "model": "qwen2.5-vl-3b",
                           "run_id": "1a2b3c4d5e6f", "said": "A letter: it opens with a salutation and is signed."]
            ] as [String: Any]
        ])
    ])
}

#Preview("Proposed kind") {
    if let proposal = ProposedKind.preview {
        ProposedKindRow(documentId: "doc-1", proposal: proposal, entityService: nil)
            .padding()
            .frame(width: 320)
    }
}
