import FicheroAPIClient
import Foundation
import Observation

/// Pages whose linked originals are in iCloud and not on this Mac (#5669, ruled by Daniel): said before Start and
/// when material is added, with the one offer, Copy into the Project, so a run never stalls page by page waiting
/// for downloads. The engine counts them, words the offer and copies (`GET /api/documents/in-icloud`, the Start
/// plan's `in_icloud`, the undoable `document.copy_into_project` action); this store asks and holds the answer.
@MainActor
@Observable
final class ICloudPagesStore {
    let client: FicheroClient

    /// What is in iCloud, with the offer; nil when nothing is.
    private(set) var pages: Components.Schemas.InIcloud?
    private(set) var isCopying = false
    private(set) var refusal: String?
    /// What the last copy said, in words.
    private(set) var copied: String?

    init(client: FicheroClient) {
        self.client = client
    }

    /// Read what is in iCloud, for the project or one folder.
    func load(folderId: String? = nil) async {
        do {
            if case .ok(let success) = try await client.api.pagesInIcloudApiDocumentsInIcloudGet(
                query: .init(folderId: folderId)
            ) {
                pages = try success.body.json
            }
        } catch {
            if error.isCancellationError { return }
            refusal = "Could not read which pages are in iCloud: \(error.localizedDescription)"
        }
    }

    /// The Start plan says the same thing in `in_icloud` (shaped as `GET /api/documents/in-icloud` answers): Ready
    /// takes it from the plan it already has.
    func adopt(fromPlan plan: Components.Schemas.StartPlan?) {
        guard let plan else { return }
        pages = plan.inIcloud.flatMap { try? Self.decode($0) }
    }

    static func decode<Body: Encodable>(_ body: Body) throws -> Components.Schemas.InIcloud {
        try JSONDecoder().decode(Components.Schemas.InIcloud.self, from: try JSONEncoder().encode(body))
    }

    /// Whether Copy into the Project can run: something to copy and room for it.
    var canCopy: Bool { (pages?.pages ?? 0) > 0 && pages?.room == true && !isCopying }

    /// Copy them into the project, as the engine's offer says: its action with its params, audited and undoable
    /// (⌘Z puts the pages back on their originals). What is in iCloud is read again after it and each undo and redo.
    @discardableResult
    func copyIntoProject(actionsService: ActionsService, steps: WindowSteps?, folderId: String? = nil) async -> Bool {
        guard canCopy, let pages else { return false }
        isCopying = true
        defer { isCopying = false }
        do {
            try await AuditedAction.run(
                pages.action, params: pages.params, actionName: "Copy into the Project",
                actionsService: actionsService, steps: steps,
                afterChange: { [weak self] in await self?.load(folderId: folderId) }
            )
            copied = "Copied \(pages.pages == 1 ? "1 page" : "\(pages.pages) pages") into the project; "
                + "they stay on this Mac now."
            return true
        } catch {
            if error.isCancellationError { return false }
            refusal = "Could not copy the pages into the project: \(error.localizedDescription)"
            return false
        }
    }
}
