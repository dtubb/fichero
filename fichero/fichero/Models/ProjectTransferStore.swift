import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let transferLogger = Logger(subsystem: "app.fichero.fichero", category: "ProjectTransfer")

/// What a drop of library items onto ANOTHER project does (#2397, #4311, `transfer.app.*` in
/// `source/moving-between-projects.md`): the Finder's grammar between projects. A drag moves, ⌥ copies, and
/// ⌘⌥ (an alias) is refused, because aliases stay within a project (`transfer.alias.not-between-projects`).
enum ProjectTransferDropDecision: Equatable {
    case move
    case copy
    case refuseAlias

    /// From the one drop grammar (`sidebarDropOperation`), sampled once at the drop entry point.
    init(_ operation: SidebarDropOperation) {
        switch operation {
        case .move: self = .move
        case .copy: self = .copy
        case .alias: self = .refuseAlias
        }
    }

    init(modifiers: SidebarDropModifiers) {
        self.init(sidebarDropOperation(modifiers: modifiers, kind: .document))
    }
}

/// One window's drop between projects: the dry run's plan shown in a small sheet, then Move or Copy, the result in
/// words, and ⌘Z on the window's step stack. The engine owns the whole transfer (`POST /api/documents/transfer`,
/// the audited `document.transfer`); the app only sends the drop and shows what the engine said.
@MainActor
@Observable
final class ProjectTransferStore {
    /// "Aliases stay within a project.", the engine's words for the same refusal.
    nonisolated static let aliasRefusal = "Aliases stay within a project."

    /// The drop waiting in the sheet.
    struct Pending: Identifiable {
        let id = UUID()
        let source: LibraryManager.LibraryReference
        let target: LibraryManager.LibraryReference
        /// Bare document ids, in the source.
        let items: [String]
        /// The folder in the target; nil: the target's Sources folder.
        let targetParentId: String?
        var mode: Components.Schemas.TransferMode
        /// The dry run's answer: what goes, what is cut and listed, the merges proposed.
        var plan: Components.Schemas.TransferResult?
        /// The engine's sentence, or the alias refusal; nothing runs while it is set.
        var refusal: String?
        /// ⌘⌥ between projects: refused, with Copy offered instead.
        var offersCopyInstead = false
        /// The transfer's answer once it ran.
        var result: Components.Schemas.TransferResult?
        var isWorking = false
    }

    var pending: Pending?

    // MARK: The drop

    /// The open project other than `target` that holds every dragged id, or nil when they are `target`'s own (or no
    /// open project has them all): a drop's project check (`transfer.app.drop-checks-project`). Ids are UUIDs, so a
    /// project's loaded documents say whose an id is without changing the drag payload.
    static func sourceProject(
        of ids: [String], target: LibraryManager.LibraryReference, among open: [LibraryManager.LibraryReference]
    ) -> LibraryManager.LibraryReference? {
        guard !ids.isEmpty else { return nil }
        let targetKnown = target.documentStore.knownDocumentsById()
        if ids.contains(where: { targetKnown[$0] != nil }) { return nil }
        return open.first { library in
            guard library.id != target.id else { return false }
            let known = library.documentStore.knownDocumentsById()
            return ids.allSatisfy { known[$0] != nil }
        }
    }

    /// The shared hook every library-item drop site calls first (sidebar folder rows, project headers, Items
    /// cells, the Items pane): when the dragged items belong to another open project, the drop becomes a transfer
    /// and this returns true; otherwise false, and the site does what it always did.
    @discardableResult
    func beginIfAcrossProjects(
        prefixedIds: [String],
        operation: SidebarDropOperation,
        into target: LibraryManager.LibraryReference?,
        parentId: String?,
        openLibraries: [LibraryManager.LibraryReference]
    ) -> Bool {
        guard let target else { return false }
        let ids = prefixedIds.filter { !$0.isEmpty && (!$0.contains(":") || $0.hasPrefix("doc:")) }
            .map { extractActualId(from: $0) }
        guard let source = Self.sourceProject(of: ids, target: target, among: openLibraries) else { return false }
        transferLogger.info("drop across projects: \(ids.count) item(s) \(source.displayName) -> \(target.displayName)")
        Task { await begin(items: ids, from: source, to: target, parentId: parentId, decision: .init(operation)) }
        return true
    }

    /// Open the sheet for a drop: ⌘⌥ is refused at once (nothing asked of the engine); a move or a copy asks the
    /// engine's dry run first.
    func begin(
        items: [String], from source: LibraryManager.LibraryReference, to target: LibraryManager.LibraryReference,
        parentId: String?, decision: ProjectTransferDropDecision
    ) async {
        let mode: Components.Schemas.TransferMode = decision == .move ? .move : .copy
        pending = Pending(source: source, target: target, items: items, targetParentId: parentId, mode: mode)
        if decision == .refuseAlias {
            pending?.refusal = Self.aliasRefusal
            pending?.offersCopyInstead = true
            return
        }
        await plan()
    }

    /// The alias refusal's Copy button: plan the same items as a copy.
    func copyInstead() async {
        guard pending != nil else { return }
        pending?.mode = .copy
        pending?.refusal = nil
        pending?.offersCopyInstead = false
        await plan()
    }

    func cancel() { pending = nil }

    // MARK: Plan and run

    /// The dry run: writes nothing; the plan, or the engine's sentence why not.
    func plan() async {
        guard let drop = pending else { return }
        pending?.isWorking = true
        defer { pending?.isWorking = false }
        switch await send(drop, dryRun: true) {
        case .success(let plan): pending?.plan = plan
        case .failure(let refusal): pending?.refusal = refusal.sentence
        }
    }

    /// Move or Copy: the transfer itself. The target gains the copies and, for a move, the source loses the items,
    /// each spliced or removed in place (never a wholesale reload); the step goes on the window's undo stack, under
    /// the target's audit row, so ⌘Z takes it back. The result stays in the sheet, in words.
    func run(undoManager: UndoManager?) async {
        guard let drop = pending, drop.refusal == nil, drop.result == nil else { return }
        pending?.isWorking = true
        defer { pending?.isWorking = false }
        switch await send(drop, dryRun: false) {
        case .failure(let refusal):
            pending?.refusal = refusal.sentence
        case .success(let result):
            pending?.result = result
            await applyLocally(result, of: drop)
            registerUndo(result, of: drop, undoManager: undoManager)
        }
    }

    private func applyLocally(_ result: Components.Schemas.TransferResult, of drop: Pending) async {
        if drop.mode == .move { drop.source.documentStore.removeDocuments(ids: Set(drop.items)) }
        let copies = result.copies ?? []
        guard !copies.isEmpty else { return }
        do {
            drop.target.documentStore.spliceDocuments(try await drop.target.documentService.getDocuments(ids: copies))
        } catch {
            // The target's change stream still delivers them; only this early splice is lost.
            transferLogger.error("could not read the copies back: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func registerUndo(_ result: Components.Schemas.TransferResult, of drop: Pending, undoManager: UndoManager?) {
        let actions = drop.target.actionsService
        // ponytail: after ⌘Z the two projects' change streams bring the rows back and take the copies away; no
        // local splice here, since the engine's inverse names no ids to splice.
        ActionUndo.register(
            auditId: result.audit,
            actionName: "\(drop.mode == .move ? "Move" : "Copy") to \(drop.target.displayName)",
            undoManager: undoManager,
            performUndo: { auditId in try await actions.undoAction(auditId: auditId).auditId }
        )
    }

    struct Refusal: Error { let sentence: String }

    /// One call to the route, through the TARGET's client: the library header names the target, the body the
    /// source (`TransferRequest`).
    private func send(_ drop: Pending, dryRun: Bool) async -> Result<Components.Schemas.TransferResult, Refusal> {
        let request = Components.Schemas.TransferRequest(
            items: drop.items, source: drop.source.url.path, targetParentId: drop.targetParentId,
            mode: drop.mode, dryRun: dryRun)
        let outcome: Result<Components.Schemas.TransferResult, Refusal>
        do {
            switch try await drop.target.ficheroClient.api.transferDocumentsApiDocumentsTransferPost(body: .json(request)) {
            case .ok(let answer):
                outcome = .success(try answer.body.json)
            case .unprocessableContent(let error):
                outcome = .failure(Refusal(sentence: (try? error.body.json)?.detail?.description
                    ?? "The engine refused the transfer."))
            case .undocumented(let code, let payload):
                outcome = .failure(Refusal(sentence: await EngineErrorDetail.message(from: payload)
                    ?? "The transfer failed (HTTP \(code))."))
            }
        } catch {
            // A transport or decoding failure (the answer did not read as a TransferResult): said, and logged whole.
            transferLogger.error("transfer call failed: \(String(describing: error), privacy: .public)")
            outcome = .failure(Refusal(sentence: "The transfer failed: \(error.localizedDescription)"))
        }
        if case .failure(let refusal) = outcome {
            transferLogger.notice("transfer \(dryRun ? "plan" : "run") refused: \(refusal.sentence, privacy: .public)")
        }
        return outcome
    }

    // MARK: Words

    /// "Move 3 items to Istmina" / "Copy 1 item to Istmina".
    static func title(_ drop: Pending) -> String {
        let count = drop.items.count
        let what = count == 1 ? "1 item" : "\(count) items"
        return "\(drop.mode == .move ? "Move" : "Copy") \(what) to \(drop.target.displayName)"
    }

    /// What goes, by kind, as the dry run counted it ("12 Document", "340 Segment"), then the files.
    static func whatGoes(_ plan: Components.Schemas.TransferResult) -> [String] {
        var lines = (plan.counts ?? []).filter { $0.planned > 0 }.map { "\($0.planned) \($0.kind)" }
        if let files = plan.files, files > 0 {
            let size = ByteCountFormatter.string(fromByteCount: Int64(plan.bytes ?? 0), countStyle: .file)
            lines.append(files == 1 ? "1 file (\(size))" : "\(files) files (\(size))")
        }
        if let linked = plan.linkedFiles, !linked.isEmpty {
            lines.append("\(linked.count) linked: the reference travels, not the file")
        }
        return lines
    }

    /// Every cut, by name: what it was and why it does not travel.
    static func cuts(_ plan: Components.Schemas.TransferResult) -> [String] {
        (plan.cuts ?? []).map { "\($0.name ?? $0.kind): \($0.reason)" }
            + (plan.leftBehind ?? []).map { "\($0.name): \($0.reason)" }
    }

    /// Each carried person or place the target may already have, proposed as a merge, never merged by itself.
    static func proposals(_ plan: Components.Schemas.TransferResult) -> [String] {
        (plan.proposals ?? []).map { "\($0.name) may be \($0.targetName) (\($0.reason))" }
    }

    /// The result in words: "Moved 3 items to Istmina. 2 links cut and listed. 1 merge proposed. ⌘Z undoes it."
    static func resultWords(_ result: Components.Schemas.TransferResult, of drop: Pending) -> String {
        let count = drop.items.count
        let what = count == 1 ? "1 item" : "\(count) items"
        var words = ["\(drop.mode == .move ? "Moved" : "Copied") \(what) to \(drop.target.displayName)."]
        let cut = (result.cuts ?? []).count
        if cut > 0 { words.append(cut == 1 ? "1 link cut and listed." : "\(cut) links cut and listed.") }
        let proposed = (result.proposals ?? []).count
        if proposed > 0 { words.append(proposed == 1 ? "1 merge proposed to review." : "\(proposed) merges proposed to review.") }
        if drop.mode == .move { words.append("The originals are in \(drop.source.displayName)'s Trash.") }
        if result.audit != nil { words.append("⌘Z undoes it.") }
        return words.joined(separator: " ")
    }
}
