import FicheroAPIClient
import Foundation
import Observation

/// Find the Documents' proposals for a folder, waiting for a person (#5550,
/// `finddocs.accept-makes-groups`): the engine's `GET /api/find-documents/proposals?folder_id=`, and
/// Accept, Reject and Accept All Above through the engine's audited actions (one undo restores). The
/// app works nothing out: what is waiting, and how sure, is what the engine answered.
///
/// One per project (`LibraryReference.foundDocumentsStore`), over THAT project's client.
@MainActor
@Observable
final class FoundDocumentsStore {
    /// One proposed document still waiting: neither accepted nor rejected.
    struct Waiting: Identifiable, Equatable {
        let proposalId: String
        let document: Components.Schemas.ProposedDocument
        var id: String { "\(proposalId)#\(document.index)" }
    }

    /// The thresholds Accept All Above offers. The engine's own default is 95%.
    static let thresholds: [Double] = [0.95, 0.9, 0.8, 0.7]

    /// What is waiting in each folder, by folder id; absent until its first read.
    private(set) var waiting: [String: [Waiting]] = [:]
    private(set) var busy = false
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// The documents still waiting in these proposals, in page order.
    nonisolated static func waiting(in proposals: [Components.Schemas.DocumentsProposal]) -> [Waiting] {
        proposals
            .flatMap { proposal in
                (proposal.documents ?? [])
                    .filter { ($0.state ?? .proposed) == .proposed }
                    .map { Waiting(proposalId: proposal.id, document: $0) }
            }
            .sorted { $0.document.firstPosition < $1.document.firstPosition }
    }

    func load(folderId: String) async {
        do {
            switch try await client.api.listFindDocumentsProposalsApiFindDocumentsProposalsGet(
                query: .init(folderId: folderId)
            ) {
            case .ok(let ok):
                let found = Self.waiting(in: try ok.body.json.items)
                if waiting[folderId] != found { waiting[folderId] = found }
                errorMessage = nil
            default:
                errorMessage = "The proposals could not be read."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func accept(_ item: Waiting, folderId: String) async {
        await change(folderId: folderId) {
            try await self.accept(proposalId: item.proposalId, .init(documentIndexes: [item.document.index]))
        }
    }

    func reject(_ item: Waiting, folderId: String) async {
        await change(folderId: folderId) {
            let response = try await self.client.api.rejectFindDocumentsProposalApiFindDocumentsProposalsProposalIdRejectPost(
                path: .init(proposalId: item.proposalId),
                body: .json(.init(documentIndexes: [item.document.index]))
            )
            guard case .ok = response else { throw FoundDocumentsError.refused }
        }
    }

    /// Accepts every waiting document at least `threshold` sure, one call per proposal.
    func acceptAll(above threshold: Double, folderId: String) async {
        let proposalIds = Set((waiting[folderId] ?? []).filter { $0.document.confidence >= threshold }.map(\.proposalId))
        await change(folderId: folderId) {
            for proposalId in proposalIds.sorted() {
                try await self.accept(proposalId: proposalId, .init(minConfidence: threshold))
            }
        }
    }

    private func accept(proposalId: String, _ request: Components.Schemas.FindDocumentsAcceptRequest) async throws {
        let response = try await client.api.acceptFindDocumentsProposalApiFindDocumentsProposalsProposalIdAcceptPost(
            path: .init(proposalId: proposalId),
            body: .json(request)
        )
        guard case .ok = response else { throw FoundDocumentsError.refused }
    }

    /// Runs one change, then reads the folder again, so the list is what the engine now holds.
    private func change(folderId: String, _ work: @escaping () async throws -> Void) async {
        busy = true
        defer { busy = false }
        var failure: String?
        do {
            try await work()
        } catch {
            failure = error.localizedDescription
        }
        await load(folderId: folderId)
        if let failure { errorMessage = failure }  // the read that follows must not hide it
    }
}

enum FoundDocumentsError: LocalizedError {
    case refused

    var errorDescription: String? { "The engine refused the change." }
}
