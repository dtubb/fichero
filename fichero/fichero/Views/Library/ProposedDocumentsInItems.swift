import FicheroAPIClient
import SwiftUI

// The documents Find the Documents proposes in a folder, in Items (`finddocs.review.items`, #5550): one row per
// document still proposed, marked Proposed with a dashed outline, holding the pages it would hold; answered in place
// by its menu, each answer the engine's audited action and one ⌘Z step (`FoundDocumentsStore`).

extension LibraryOutlineNode {
    /// The folder's rows with each waiting proposal in place of its pages: the proposal's row stands where its first
    /// listed page stood, and holds its pages, in the proposal's order, as page rows. A page in no waiting proposal
    /// stays a loose row; a proposal none of whose pages is listed (filtered out) is not shown.
    static func withProposals(
        _ nodes: [LibraryOutlineNode], waiting: [FoundDocumentsStore.Waiting], folder: Document
    ) -> [LibraryOutlineNode] {
        guard !waiting.isEmpty else { return nodes }
        var owner: [String: Int] = [:]
        for (index, item) in waiting.enumerated() {
            for pageId in item.document.pageIds { owner[pageId] = index }
        }
        var listed: [String: Document] = [:]
        for node in nodes {
            if case .document = node.kind, owner[node.document.id] != nil { listed[node.document.id] = node.document }
        }
        var placed = Set<Int>()
        var rows: [LibraryOutlineNode] = []
        for node in nodes {
            guard case .document = node.kind, let index = owner[node.document.id] else {
                rows.append(node)
                continue
            }
            guard placed.insert(index).inserted else { continue }
            let item = waiting[index]
            let pages = item.document.pageIds.compactMap { listed[$0] }.map { pageItem($0, parent: folder) }
            rows.append(proposedDocument(item, folder: folder, pages: pages))
        }
        return rows
    }

    /// What a menu over these selected rows answers: the proposed documents selected (a proposal's row, or one of
    /// its pages), and the one page when a single page row is selected.
    struct ProposalTarget: Equatable {
        let documents: [FoundDocumentsStore.Waiting]
        let pageId: String?
    }

    /// The proposals the selected row ids name, in page order; nil when the selection names none.
    static func proposalTarget(
        for ids: Set<String>, waiting: [FoundDocumentsStore.Waiting], folderId: String
    ) -> ProposalTarget? {
        var chosen: [String: FoundDocumentsStore.Waiting] = [:]
        var page: String?
        for id in ids {
            if id.hasPrefix(proposedPrefix) {
                let waitingId = String(id.dropFirst(proposedPrefix.count))
                if let item = waiting.first(where: { $0.id == waitingId }) { chosen[item.id] = item }
                continue
            }
            let parsed = parse(nodeId: id)
            guard parsed.childType == .pages, parsed.documentId == folderId, let pageId = parsed.itemId,
                  let item = waiting.first(where: { $0.document.pageIds.contains(pageId) }) else { continue }
            chosen[item.id] = item
            if ids.count == 1 { page = pageId }
        }
        guard !chosen.isEmpty else { return nil }
        let documents = chosen.values.sorted { $0.document.firstPosition < $1.document.firstPosition }
        return ProposalTarget(documents: documents, pageId: page)
    }
}

/// A person's answer to proposed documents, from the Items menu.
enum ProposalAnswer: Equatable {
    case accept, reject, join
    case split(pageId: String)
    case movePage(FoundDocumentsStore.Neighbour)
}

extension LibraryView {
    /// The folder shown, when it is a folder with proposals waiting; and what waits in it.
    private var shownProposals: (folder: Document, waiting: [FoundDocumentsStore.Waiting])? {
        guard let folderId = shownFolderDocumentId, let folder = documentStore.selectedCollection,
              folder.id == folderId,
              let waiting = activeLibraryReference?.foundDocumentsStore.waiting[folderId], !waiting.isEmpty else {
            return nil
        }
        return (folder, waiting)
    }

    /// The outline's rows with the shown folder's proposals in place of their pages.
    func withShownProposals(_ nodes: [LibraryOutlineNode]) -> [LibraryOutlineNode] {
        guard let shown = shownProposals else { return nodes }
        return LibraryOutlineNode.withProposals(nodes, waiting: shown.waiting, folder: shown.folder)
    }

    /// What the menu over these rows answers, when they name proposed documents.
    func proposalTarget(for ids: Set<String>) -> LibraryOutlineNode.ProposalTarget? {
        guard let shown = shownProposals else { return nil }
        return LibraryOutlineNode.proposalTarget(for: ids, waiting: shown.waiting, folderId: shown.folder.id)
    }

    /// Answer through the project's store: the engine's audited action, one ⌘Z step, then the folder read again.
    func answerProposals(_ answer: ProposalAnswer, target: LibraryOutlineNode.ProposalTarget) {
        guard let folderId = shownFolderDocumentId, let library = activeLibraryReference,
              let first = target.documents.first else { return }
        let store = library.foundDocumentsStore
        let documents = documentStore
        // Accepting makes group nodes, and undoing takes them away: the folder's rows are read again each time.
        let answering = FoundDocumentsStore.Answering(
            actions: library.actionsService, steps: windowSteps, afterChange: { await documents.refresh() }
        )
        Task {
            switch answer {
            case .accept: await store.accept(target.documents, folderId: folderId, via: answering)
            case .reject: await store.reject(target.documents, folderId: folderId, via: answering)
            case .join: await store.join(first, folderId: folderId, via: answering)
            case .split(let pageId): await store.split(first, at: pageId, folderId: folderId, via: answering)
            case .movePage(let neighbour): await store.movePage(first, to: neighbour, folderId: folderId, via: answering)
            }
        }
    }
}

/// The menu over proposed rows: Accept and Reject for every proposed document selected; for one, the adjustments
/// that change which pages belong.
struct ProposedDocumentsMenu: View {
    let target: LibraryOutlineNode.ProposalTarget
    let perform: (ProposalAnswer) -> Void

    struct Offer: Equatable {
        let title: String
        let answer: ProposalAnswer
    }

    /// What the menu offers, in order. Accept and Reject always; for one document, Split Here on a page that is
    /// not its first, Move Page on its first page (to the document before) or its last (to the one after) when
    /// that neighbour is still proposed and the page is not the document's only one, and Join with Next.
    static func offers(for target: LibraryOutlineNode.ProposalTarget) -> [Offer] {
        let count = target.documents.count
        var offers = [Offer(title: FoundDocumentsStore.named("Accept", count), answer: .accept),
                      Offer(title: FoundDocumentsStore.named("Reject", count), answer: .reject)]
        guard count == 1, let item = target.documents.first else { return offers }
        let pages = item.document.pageIds
        if let pageId = target.pageId {
            if pageId != pages.first { offers.append(Offer(title: "Split Here", answer: .split(pageId: pageId))) }
            if pages.count > 1, pageId == pages.first, item.previousIsOpen {
                offers.append(Offer(title: "Move Page to Previous Document", answer: .movePage(.previous)))
            }
            if pages.count > 1, pageId == pages.last, item.nextIsOpen {
                offers.append(Offer(title: "Move Page to Next Document", answer: .movePage(.next)))
            }
        }
        if item.nextIsOpen { offers.append(Offer(title: "Join with Next Document", answer: .join)) }
        return offers
    }

    var body: some View {
        let offers = Self.offers(for: target)
        ForEach(Array(offers.enumerated()), id: \.offset) { index, offer in
            if index == 2 { Divider() }
            Button(offer.title) { perform(offer.answer) }
        }
    }
}

/// A proposed document's Name cell: a dashed "Proposed" mark, its name, then its pages, kind and how sure.
struct ProposedDocumentNameCell: View {
    let proposal: Components.Schemas.ProposedDocument

    /// "Pages 3–5 · Sentencia · 82% sure".
    static func detail(of proposal: Components.Schemas.ProposedDocument) -> String {
        let first = proposal.firstPosition + 1, last = proposal.lastPosition + 1
        let pages = first == last ? "Page \(first)" : "Pages \(first)–\(last)"
        let sure = proposal.confidence.formatted(.percent.precision(.fractionLength(0))) + " sure"
        return [pages, proposal.kind, sure].compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 6) {
            Text("Proposed")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 5)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .strokeBorder(.secondary, style: StrokeStyle(lineWidth: 1, dash: [3, 2]))
                )
            Text(proposal.name)
                .lineLimit(1)
            Text(Self.detail(of: proposal))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .help((proposal.reasons ?? []).joined(separator: "; "))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Proposed document: \(proposal.name), \(Self.detail(of: proposal))")
        .accessibilityIdentifier("items.proposedDocument")
    }
}

/// Reads the shown folder's proposals when the folder changes, so Items can show them.
struct ProposedDocumentsLoader: ViewModifier {
    let store: FoundDocumentsStore?
    let folderId: String?

    func body(content: Content) -> some View {
        content.task(id: folderId) {
            guard let store, let folderId else { return }
            await store.load(folderId: folderId)
        }
    }
}

#Preview("Proposed document rows") {
    VStack(alignment: .leading, spacing: 8) {
        ProposedDocumentNameCell(proposal: .init(
            index: 0, name: "Sentencia, 1948", pageIds: ["a", "b", "c"], firstPosition: 2, lastPosition: 4,
            kind: "Sentencia", confidence: 0.82, reasons: ["VISTOS at the head of page 3"]
        ))
        ProposedDocumentNameCell(proposal: .init(
            index: 1, name: "Carta", pageIds: ["d"], firstPosition: 5, lastPosition: 5,
            kind: nil, confidence: 0.64, reasons: []
        ))
    }
    .padding()
    .frame(width: 480)
}
