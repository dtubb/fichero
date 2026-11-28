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
    /// The last answer for the whole project; a folder's read never writes it. The at-open relink and the alert
    /// read this one, so a folder's answer arriving in between does not decide them (#7077).
    private(set) var projectMissing: Components.Schemas.MissingOriginals?
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
    /// The last relink in one sentence, "Relinked 214. Still missing: 2." (#5535, #6733).
    private(set) var summarySentence: String?
    /// Where this project's originals were last relinked to (#5535): kept after a relink, tried at the next open. A
    /// test's stand-ins replace them.
    @ObservationIgnored lazy var rememberRoot: (URL) -> Void = { [client] folder in
        RememberedOriginalsRoot.remember(folder, project: client.currentLibraryPath)
    }
    @ObservationIgnored lazy var recallRoot: () -> URL? = { [client] in
        RememberedOriginalsRoot.recall(project: client.currentLibraryPath)
    }
    /// The alert offering Locate… / Not Now is showing (#7077).
    var isOffering = false
    /// That alert has been shown for this open of the project (this store lives as long as the open project).
    private var offered = false
    /// A missing original has asked for the project's originals this run; the remembered folder has been tried.
    private var askedThisRun = false
    private var triedRememberedRoot = false

    /// Open Locate Originals, for the project or one folder.
    func begin(folderId: String? = nil) {
        cancel()
        self.folderId = folderId
        isChoosing = true
    }

    /// At open, once: when originals are missing, offer Locate… in an alert. Nothing missing, or Locate Originals
    /// already open, offers nothing and is not counted as this open's offer. Returns whether it offered.
    @discardableResult
    func offerOnce() -> Bool {
        guard !offered, !isChoosing, (projectMissing?.pages ?? 0) > 0 else { return false }
        offered = true
        isOffering = true
        return true
    }

    func declineOffer() { isOffering = false }

    func locateFromOffer() {
        isOffering = false
        begin()
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
                let answer = try success.body.json
                missing = answer
                if folderId == nil { projectMissing = answer }
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
        var granted = false
        do {
            plan = try await FolderAccessManager.grantThenEngineWork(
                grant: {
                    try await grant(folder)
                    granted = true
                },
                engineWork: { try await requestPlan(folder, folderId: folderId) }
            )
        } catch {
            if error.isCancellationError { return }
            // Name the step that failed (#6733): a refused grant means the engine was never asked to look.
            refusal = granted
                ? "Could not look in \(folder.lastPathComponent): \(error.localizedDescription)"
                : "Fichero could not get access to \(folder.lastPathComponent), so nothing was looked for: \(error.localizedDescription)"
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
            summarySentence = Self.summary(
                relinked: plan.matched.count, of: plan.matched.count + plan.notFound.count + plan.ambiguous.count
            )
            rememberRoot(newRoot)
            self.plan = nil
            return true
        } catch {
            if error.isCancellationError { return false }
            refusal = "Could not relink the originals: \(error.localizedDescription)"
            return false
        }
    }

    /// A page whose original is missing asks for the PROJECT's originals, at most once a run (#5535): one Locate
    /// Originals, never a folder panel per file or folder. `force` is a person's own Retry. Returns whether it opened.
    @discardableResult
    func askOnce(force: Bool = false) -> Bool {
        guard force || !askedThisRun else { return false }
        askedThisRun = true
        begin()
        return true
    }

    /// At open (#5535): a project whose originals are missing relinks from the folder it was last relinked to, with
    /// no panel; Locate Originals is asked for only if that leaves something missing. Once a run. Returns whether
    /// it relinked.
    @discardableResult
    func relinkFromRememberedRoot(actionsService: ActionsService, steps: WindowSteps?) async -> Bool {
        guard !triedRememberedRoot, (projectMissing?.pages ?? 0) > 0 else { return false }
        triedRememberedRoot = true
        guard let root = recallRoot() else { return false }
        await choose(root)
        guard plan?.matched.isEmpty == false else {
            cancel()
            return false
        }
        return await relink(actionsService: actionsService, steps: steps)
    }

    /// The relink in one sentence: how many of the missing were found, and how many are still missing.
    static func summary(relinked: Int, of total: Int) -> String {
        let still = total - relinked
        return "Relinked \(relinked)." + (still > 0 ? " Still missing: \(still)." : "")
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
