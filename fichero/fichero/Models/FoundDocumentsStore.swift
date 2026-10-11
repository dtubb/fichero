import FicheroAPIClient
import Foundation
import Observation

/// Find the Documents' proposals for a folder, waiting for a person (#5550, `finddocs.accept-makes-groups`,
/// `finddocs.review.items`): the engine's `GET /api/find-documents/proposals?folder_id=`, and the person's answers
/// (Accept, Reject, Accept All Above, and the adjustments Split, Join and Move Page) as the engine's audited actions
/// through `POST /api/actions/invoke`, each answer one ⌘Z step. The app works nothing out: what is waiting, and how
/// sure, is what the engine answered.
///
/// One per project (`LibraryReference.foundDocumentsStore`), over THAT project's client.
@MainActor
@Observable
final class FoundDocumentsStore {
    /// One proposed document still waiting: neither accepted nor rejected.
    struct Waiting: Identifiable, Hashable {
        let proposalId: String
        let document: Components.Schemas.ProposedDocument
        /// The document before it in its proposal is still proposed, so a first page can move to it.
        var previousIsOpen = false
        /// The document after it is still proposed, so a last page can move to it, or it can join it.
        var nextIsOpen = false
        var id: String { "\(proposalId)#\(document.index)" }
    }

    /// Where Move Page sends a page: the document before (its first page) or after (its last page).
    enum Neighbour: String, Encodable {
        case previous, next
    }

    /// The thresholds Accept All Above offers. The engine's own default is 95%.
    static let thresholds: [Double] = [0.95, 0.9, 0.8, 0.7]

    /// What is waiting in each folder, by folder id; absent until its first read.
    private(set) var waiting: [String: [Waiting]] = [:]
    private(set) var busy = false
    var errorMessage: String?

    let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The documents still waiting in these proposals, in page order.
    nonisolated static func waiting(in proposals: [Components.Schemas.DocumentsProposal]) -> [Waiting] {
        proposals
            .flatMap { proposal in
                let documents = proposal.documents ?? []
                let open = Set(documents.filter(Self.isOpen).map(\.index))
                return documents.filter(Self.isOpen).map {
                    Waiting(proposalId: proposal.id, document: $0,
                            previousIsOpen: open.contains($0.index - 1), nextIsOpen: open.contains($0.index + 1))
                }
            }
            .sorted { $0.document.firstPosition < $1.document.firstPosition }
    }

    nonisolated private static func isOpen(_ document: Components.Schemas.ProposedDocument) -> Bool {
        (document.state ?? .proposed) == .proposed
    }

    /// The waiting document a page is in, in this folder, if any.
    func waiting(holding pageId: String, folderId: String) -> Waiting? {
        waiting[folderId]?.first { $0.document.pageIds.contains(pageId) }
    }

    func load(folderId: String) async {
        do {
            switch try await client.api.listFindDocumentsProposalsApiFindDocumentsProposalsGet(
                query: .init(folderId: folderId)
            ) {
            case .ok(let response):
                let found = Self.waiting(in: try response.body.json.items)
                if waiting[folderId] != found { waiting[folderId] = found }
                errorMessage = nil
            default:
                errorMessage = "The proposals could not be read."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = error.localizedDescription
        }
    }

    /// How often a run is asked whether it has ended.
    var pollInterval: Duration = .seconds(3)

    /// Follow a Find the Documents run until it ends, then read again every folder read so far (the one Items or
    /// the Inspector shows among them), so its proposals appear without leaving the folder.
    func follow(run jobId: String) async {
        let underWay: Set<String> = ["queued", "waiting", "pending", "running", "paused"]
        while !Task.isCancelled {
            guard case .ok(let response)? = try? await client.api.findDocumentsRunApiFindDocumentsRunsJobIdGet(
                path: .init(jobId: jobId)
            ), let run = try? response.body.json, underWay.contains(run.state) else { break }
            try? await Task.sleep(for: pollInterval)
        }
        for folderId in waiting.keys.sorted() { await load(folderId: folderId) }
    }

    // MARK: - Answers (each one ⌘Z step)

    /// Where an answer is sent and stepped: the project's actions, the window's ⌘Z stack, and what to read again
    /// after it and after each undo and redo besides the folder's proposals.
    struct Answering {
        let actions: ActionLibraryService
        let steps: WindowSteps?
        var afterChange: @MainActor () async -> Void = {}
    }

    /// Accept these documents: one `finddocs.accept` per proposal they belong to, one step for all of them.
    func accept(_ items: [Waiting], folderId: String, via answering: Answering) async {
        await answer(Self.named("Accept", items.count), folderId: folderId, via: answering,
                     calls: Self.byProposal(items).map { proposalId, indexes in
                         ("finddocs.accept", FoundDocumentsAnswerParams(proposalId: proposalId, documentIndexes: indexes))
                     })
    }

    /// Reject these documents: one `finddocs.reject` per proposal, one step for all of them.
    func reject(_ items: [Waiting], folderId: String, via answering: Answering) async {
        await answer(Self.named("Reject", items.count), folderId: folderId, via: answering,
                     calls: Self.byProposal(items).map { proposalId, indexes in
                         ("finddocs.reject", FoundDocumentsAnswerParams(proposalId: proposalId, documentIndexes: indexes))
                     })
    }

    /// Accept every waiting document at least `threshold` sure: the engine applies the threshold, one call per
    /// proposal holding something that sure, one step for all of them.
    func acceptAll(above threshold: Double, folderId: String, via answering: Answering) async {
        let proposalIds = Set((waiting[folderId] ?? []).filter { $0.document.confidence >= threshold }.map(\.proposalId))
        await answer("Accept All at Least \(threshold.formatted(.percent)) Sure", folderId: folderId, via: answering,
                     calls: proposalIds.sorted().map {
                         ("finddocs.accept", FoundDocumentsAnswerParams(proposalId: $0, minConfidence: threshold))
                     })
    }

    /// Split a proposed document so `pageId` (one of its pages, not its first) starts a new one.
    func split(_ item: Waiting, at pageId: String, folderId: String, via answering: Answering) async {
        let params = FoundDocumentsAdjustParams(proposalId: item.proposalId, documentIndex: item.document.index,
                                                pageId: pageId)
        await answer("Split Document", folderId: folderId, via: answering, calls: [("finddocs.split", params)])
    }

    /// Join a proposed document to the one after it.
    func join(_ item: Waiting, folderId: String, via answering: Answering) async {
        let params = FoundDocumentsAdjustParams(proposalId: item.proposalId, documentIndex: item.document.index)
        await answer("Join Documents", folderId: folderId, via: answering, calls: [("finddocs.join", params)])
    }

    /// Move a proposed document's first page to the document before it, or its last page to the one after.
    func movePage(_ item: Waiting, to neighbour: Neighbour, folderId: String, via answering: Answering) async {
        let name = neighbour == .previous ? "Move Page to Previous Document" : "Move Page to Next Document"
        let params = FoundDocumentsAdjustParams(proposalId: item.proposalId, documentIndex: item.document.index,
                                                neighbour: neighbour)
        await answer(name, folderId: folderId, via: answering, calls: [("finddocs.move_page", params)])
    }

    /// Runs one answer's calls as one ⌘Z step (`undo.batches`), then reads the folder again (and after each undo
    /// and redo), so the list is what the engine now holds. A refusal is said in the engine's words.
    private func answer(_ name: String, folderId: String, via answering: Answering,
                        calls: [(String, any Encodable)]) async {
        guard !calls.isEmpty else { return }
        busy = true
        defer { busy = false }
        let afterChange = answering.afterChange
        let reread: @MainActor () async -> Void = { [weak self] in
            await self?.load(folderId: folderId)
            await afterChange()
        }
        let actions = answering.actions
        var failure: String?
        do {
            try await UndoableChange.batch(
                calls, named: { _ in name }, service: actions, steps: answering.steps, afterEach: reread,
                change: { call in
                    [try await actions.invokeAction(name: call.0, params: AnyEncodableParams(call.1)).auditId]
                }
            )
        } catch {
            failure = Self.words(of: error)
        }
        await reread()
        if let failure { errorMessage = failure }  // the read that follows must not hide it
    }

    // MARK: - Helpers

    static func byProposal(_ items: [Waiting]) -> [(String, [Int])] {
        let grouped = Dictionary(grouping: items, by: \.proposalId)
        return grouped.keys.sorted().map { key in (key, grouped[key, default: []].map(\.document.index).sorted()) }
    }

    static func named(_ verb: String, _ count: Int) -> String {
        UndoableChange.named(verb, count: count, one: "Document", many: "Documents")
    }

    /// The engine's own sentence from a refused action, without the transport's "HTTP 409:".
    static func words(of error: Error) -> String {
        if case APIError.httpError(_, let message) = error { return message }
        return error.localizedDescription
    }
}

/// `finddocs.accept` / `finddocs.reject`'s params.
struct FoundDocumentsAnswerParams: Encodable {
    let proposalId: String
    var documentIndexes: [Int]?
    var minConfidence: Double?

    enum CodingKeys: String, CodingKey {
        case proposalId = "proposal_id", documentIndexes = "document_indexes", minConfidence = "min_confidence"
    }
}

/// `finddocs.split` / `.join` / `.move_page`'s params.
struct FoundDocumentsAdjustParams: Encodable {
    let proposalId: String
    let documentIndex: Int
    var pageId: String?
    /// Move Page's `to`: the document before or after.
    var neighbour: FoundDocumentsStore.Neighbour?

    enum CodingKeys: String, CodingKey {
        case proposalId = "proposal_id", documentIndex = "document_index", pageId = "page_id", neighbour = "to"
    }
}

/// An `any Encodable` as a concrete `Encodable`, for one action call among several of different shapes.
private struct AnyEncodableParams: Encodable {
    let wrapped: any Encodable
    init(_ wrapped: any Encodable) { self.wrapped = wrapped }
    func encode(to encoder: Encoder) throws { try wrapped.encode(to: encoder) }
}
