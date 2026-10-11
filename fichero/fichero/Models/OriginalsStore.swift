import FicheroAPIClient
import Foundation
import Observation

/// Locate Originals (#5672): the project's linked pages whose originals are no longer where it says (moved,
/// renamed, on a drive that is not plugged in), said plainly in one place; then a folder the person points at, the
/// engine's plan for it in words (matched, not found, ambiguous), and Relink, one audited action with ⌘Z. The engine
/// matches and writes (`GET /api/documents/missing-originals`, `POST /api/documents/relink-originals/plan`, the
/// `document.relink_originals` action); this store asks and holds the answers.
@MainActor
@Observable
final class OriginalsStore {
    let client: FicheroClient

    /// The missing originals, or nil when none are (or before they are read).
    private(set) var missing: Components.Schemas.MissingOriginals?
    /// What relinking to the chosen folder would do, before it is done.
    private(set) var plan: Components.Schemas.RelinkPlan?
    /// The folder chosen, for the plan and the relink.
    private(set) var newRoot: URL?
    /// One folder's pages only; nil: the project's.
    private(set) var folderId: String?
    private(set) var isWorking = false
    private(set) var refusal: String?
    /// How the engine is given access to the chosen folder before it looks (a security-scoped grant); a test's
    /// stand-in replaces it.
    var grant: (URL) async throws -> Void = { try await FolderAccessManager.shared.saveBookmarkIfDirectory($0) }
    /// Locate Originals is open (File › Locate Originals…, an item's menu, the Items pane's notice).
    var isChoosing = false

    /// Open Locate Originals, for the project or one folder.
    func begin(folderId: String? = nil) {
        cancel()
        self.folderId = folderId
        isChoosing = true
    }

    init(client: FicheroClient) {
        self.client = client
    }

    /// Whether this page's original is missing (`missing.ids`).
    func isMissing(_ documentId: String) -> Bool { missing?.ids.contains(documentId) ?? false }

    /// Read which originals are missing, for the project or one folder.
    func loadMissing(folderId: String? = nil) async {
        do {
            if case .ok(let success) = try await client.api.missingOriginalsApiDocumentsMissingOriginalsGet(
                query: .init(folderId: folderId)
            ) {
                missing = try success.body.json
            }
        } catch {
            if error.isCancellationError { return }
            refusal = "Could not read which originals are missing: \(error.localizedDescription)"
        }
    }

    /// The person chose the folder the originals are in now: grant the engine access to it, then ask what
    /// relinking to it would do. Nothing is written.
    func choose(_ folder: URL, folderId: String? = nil) async {
        newRoot = folder
        self.folderId = folderId
        plan = nil
        refusal = nil
        isWorking = true
        defer { isWorking = false }
        do {
            plan = try await FolderAccessManager.grantThenEngineWork(
                grant: { try await grant(folder) },
                engineWork: { try await requestPlan(folder, folderId: folderId) }
            )
        } catch {
            if error.isCancellationError { return }
            refusal = "Could not look in \(folder.lastPathComponent): \(error.localizedDescription)"
        }
    }

    private func requestPlan(_ folder: URL, folderId: String?) async throws -> Components.Schemas.RelinkPlan? {
        let response = try await client.api.planRelinkOriginalsApiDocumentsRelinkOriginalsPlanPost(
            body: .json(.init(newRoot: folder.path, folderId: folderId))
        )
        switch response {
        case .ok(let success):
            return try success.body.json
        case .unprocessableContent:
            refusal = "Fichero could not plan relinking to \(folder.lastPathComponent)."
        case .undocumented(let code, let payload):
            refusal = await EngineErrorDetail.message(from: payload) ?? "Could not plan the relink (HTTP \(code))."
        }
        return nil
    }

    /// Relink what the plan matched, as one audited action, ⌘Z registered (`document.relink_originals`); the
    /// missing originals are read again after it, and after its undo and redo. Returns whether it ran.
    @discardableResult
    func relink(actionsService: ActionsService, steps: WindowSteps?) async -> Bool {
        guard let newRoot, let plan, !plan.matched.isEmpty else { return false }
        isWorking = true
        defer { isWorking = false }
        do {
            let folder = folderId
            try await AuditedAction.run(
                "document.relink_originals", params: RelinkOriginalsRequest(newRoot: newRoot.path, folderId: folder),
                actionName: "Locate Originals", actionsService: actionsService, steps: steps,
                afterChange: { [weak self] in await self?.loadMissing(folderId: folder) }
            )
            self.plan = nil
            return true
        } catch {
            if error.isCancellationError { return false }
            refusal = "Could not relink the originals: \(error.localizedDescription)"
            return false
        }
    }

    /// Put the chooser back to nothing chosen.
    func cancel() {
        plan = nil
        newRoot = nil
        refusal = nil
    }

    /// The plan in words, one line per list, for the sheet: the engine's sentence, then what each list means.
    static func lines(of plan: Components.Schemas.RelinkPlan) -> [String] {
        var lines = [plan.sentence]
        if !plan.matched.isEmpty { lines.append("Relinked to the new place: \(plan.matched.count).") }
        if !plan.notFound.isEmpty { lines.append("Not found there, left as they are: \(plan.notFound.count).") }
        if !plan.ambiguous.isEmpty { lines.append("More than one file matches, left for you: \(plan.ambiguous.count).") }
        if !plan.folders.isEmpty { lines.append("Folders that move with them: \(plan.folders.count).") }
        return lines
    }
}

/// `document.relink_originals`'s params, as the plan route takes them.
struct RelinkOriginalsRequest: Encodable, Equatable {
    let newRoot: String
    let folderId: String?

    enum CodingKeys: String, CodingKey {
        case newRoot = "new_root"
        case folderId = "folder_id"
    }
}
