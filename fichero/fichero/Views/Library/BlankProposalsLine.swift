import SwiftUI

/// Pages the run was unsure were blank (`prep.unsure-becomes-a-proposal`, `prep.check.blank-mark-is-a-correction`): kept
/// and shown, with the run's proposal stored on the page (`metadata.prep_proposals.blank`). One "N may be blank" line
/// lists them with the run's reason in words; Hide and Keep are a person's word, each one audited action with Undo.
enum BlankProposals {
    /// The run's reason for a page with an open blank proposal, nil for a page without one.
    static func reason(_ document: Document) -> String? {
        guard !document.excludeFromProcessing,
              let proposals = document.metadata["prep_proposals"]?.value as? [String: Any],
              let blank = proposals["blank"] as? [String: Any] else { return nil }
        return blank["reason"] as? String ?? "The run is not sure this page is blank"
    }

    static func proposed(in documents: [Document]) -> [Document] { documents.filter { reason($0) != nil } }

    static func line(_ count: Int) -> String { "\(count) may be blank" }

    /// The page after a person's answer, as the engine leaves it: the proposal gone, the person's word on the mark.
    static func answered(_ document: Document, blank: Bool) -> Document {
        var page = document
        page.excludeFromProcessing = blank
        var proposals = (document.metadata["prep_proposals"]?.value as? [String: Any]) ?? [:]
        proposals["blank"] = nil
        page.metadata["prep_proposals"] = AnyCodable(proposals)
        page.metadata["blank"] = AnyCodable(["blank": blank, "by": "person"] as [String: Any])
        return page
    }
}

/// The "N may be blank" line above the rows; nothing when no page has an open proposal.
struct BlankProposalsLine: View {
    let documents: [Document]
    let store: DocumentStore

    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var expanded = false
    @State private var failure: String?

    var body: some View {
        let proposed = BlankProposals.proposed(in: documents)
        if !proposed.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    expanded.toggle()
                } label: {
                    Label(BlankProposals.line(proposed.count), systemImage: "questionmark.square.dashed")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("library.blankProposals")
                if expanded {
                    ForEach(proposed) { page in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(page.name).font(.callout).lineLimit(1)
                                Spacer()
                                Button("Hide") { Task { await answer(page, blank: true) } }
                                    .controlSize(.small)
                                    .accessibilityIdentifier("library.blankProposal.hide")
                                Button("Keep") { Task { await answer(page, blank: false) } }
                                    .controlSize(.small)
                                    .accessibilityIdentifier("library.blankProposal.keep")
                            }
                            if let reason = BlankProposals.reason(page) {
                                Text(reason).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)
        }
    }

    private func answer(_ page: Document, blank: Bool) async {
        guard let actionsService = actionStore?.actionsService else { return }
        do {
            var first = true
            try await AuditedAction.run(
                "image.mark_blank", params: ImageMarkBlankRequest(documentId: page.id, blank: blank),
                actionName: blank ? "Hide Page" : "Keep Page", actionsService: actionsService, steps: windowSteps,
                afterChange: {
                    await HiddenPages.settle(
                        store, id: page.id, fallback: first ? BlankProposals.answered(page, blank: blank) : nil)
                    first = false
                }
            )
            failure = nil
        } catch {
            failure = "Couldn't answer for \(page.name): \(error.localizedDescription)"
        }
    }
}

#Preview("Blank proposals line") {
    let unsure = Document(
        name: "IMG_0007",
        metadata: ["prep_proposals": AnyCodable(
            ["blank": ["reason": "very little ink beyond its ruling: kept, not hidden", "by": "run r1"]] as [String: Any])])
    BlankProposalsLine(documents: [unsure], store: DocumentStore.preview)
        .frame(width: 360)
}
