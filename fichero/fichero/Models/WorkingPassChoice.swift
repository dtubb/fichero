import Foundation

/// "Make Working" (#5156): a person chooses which of a page's passes is the working one -- the one its
/// text and edits come from, and the one the Source view draws first. The audited
/// `pass.choose_working`; ⌘Z by its own audit id (a page's first choice undoes to the project's rule).
enum WorkingPassChoice {
    typealias Params = WorkingPassChooseParams

    /// Send it, register ⌘Z, and re-read the page's segments (which moves the store's revision, so the
    /// Source view redraws from the newly working pass) after the choice and after each undo / redo.
    @MainActor
    @discardableResult
    static func run(
        documentId: String, passId: String, actionsService: ActionsService, store: SegmentStore,
        undoManager: UndoManager?
    ) async throws -> String {
        let params = Params(documentId: documentId, passId: passId)
        let result = try await actionsService.invokeAction(name: "pass.choose_working", params: params)
        ActionUndo.register(
            auditId: result.auditId, actionName: "Make Working", undoManager: undoManager,
            performUndo: { auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await store.load(documentId: documentId, force: true)
                return next
            }
        )
        await store.load(documentId: documentId, force: true)
        return result.auditId
    }
}

/// `pass.choose_working`'s params (top level: SwiftLint's nesting rule counts CodingKeys).
struct WorkingPassChooseParams: Encodable, Equatable {
    let documentId: String
    let passId: String

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", passId = "pass_id"
    }
}

/// Delete a pass (#5227): the audited `segment.pass_delete` -- a soft delete; ⌘Z restores it by its audit id.
/// A pass still read from an older result (`legacy:…`) is not a row yet, so it has nothing to delete.
enum PassDeletion {
    static func canDelete(_ passId: String) -> Bool { !passId.hasPrefix("legacy:") }

    @MainActor
    static func run(
        documentId: String, passId: String, actionsService: ActionsService, store: SegmentStore,
        undoManager: UndoManager?
    ) async throws {
        let result = try await actionsService.invokeAction(name: "segment.pass_delete", params: PassDeleteParams(passId: passId))
        ActionUndo.register(
            auditId: result.auditId, actionName: "Delete Pass", undoManager: undoManager,
            performUndo: { auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await store.load(documentId: documentId, force: true)
                return next
            }
        )
        await store.load(documentId: documentId, force: true)
    }
}

struct PassDeleteParams: Encodable, Equatable {
    let passId: String

    enum CodingKeys: String, CodingKey { case passId = "pass_id" }
}
