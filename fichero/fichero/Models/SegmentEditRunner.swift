import Foundation

/// Sends a `SegmentEdit.Call` through the audited choke point and registers ⌘Z for it by its own
/// audit id, then re-reads the page's segments so the boxes show the result.
@MainActor
struct SegmentEditRunner {
    /// Posted ONCE per change this runner makes -- the edit, its ⌘Z, its ⇧⌘Z -- with the page's id as
    /// `object`, after the store has re-read it. A surface that shows the page but did not make the
    /// edit re-reads it on this (#5171: a direction set in the Segment menu or the Inspector reaches the
    /// Reader now, not on its next open). One post per change, never a poll.
    static let didChange = Notification.Name("SegmentEditRunner.didChange")

    let actionsService: ActionsService
    let store: SegmentStore

    /// Answers the audit id the edit wrote.
    @discardableResult
    func run(
        _ call: SegmentEdit.Call, documentId: String, actionName: String, steps: WindowSteps?,
        afterChange: @escaping @MainActor () async -> Void = {}
    ) async throws -> String {
        try await runAnswering(call, documentId: documentId, actionName: actionName, steps: steps, afterChange: afterChange)
            .auditId
    }

    /// `run`, answering the engine's whole result (the Knife says how many lines it cut and left alone).
    func runAnswering(
        _ call: SegmentEdit.Call, documentId: String, actionName: String, steps: WindowSteps?,
        afterChange: @escaping @MainActor () async -> Void = {}
    ) async throws -> ActionInvokeResult {
        let store = store
        let result = try await AuditedAction.run(
            call.action, params: call.params, actionName: actionName, actionsService: actionsService, steps: steps,
            afterChange: {
                await store.load(documentId: documentId, force: true)
                await afterChange()
                NotificationCenter.default.post(name: SegmentEditRunner.didChange, object: documentId)
            }
        )
        return result
    }
}

/// Re-reads a page on `SegmentEditRunner.didChange`: the Reader's hold on segment edits made elsewhere
/// (#5171). `reload` gets the changed page's id; whether that page is on screen is its call.
@MainActor
final class SegmentChangeObserver {
    nonisolated(unsafe) private var token: (any NSObjectProtocol)?

    nonisolated(unsafe) private var sourceToken: (any NSObjectProtocol)?

    /// `reload` gets the changed page's id, or nil for EVERY page shown: a direction stated on a source
    /// (`SourceDirection.didChange`) reaches every page below it.
    init(reload: @escaping @MainActor @Sendable (String?) async -> Void) {
        token = NotificationCenter.default.addObserver(
            forName: SegmentEditRunner.didChange, object: nil, queue: .main
        ) { note in
            guard let pageId = note.object as? String else { return }
            Task { @MainActor in await reload(pageId) }
        }
        // ponytail: every shown page, not only those under the node; filter by ancestry if a Reader of many pages makes this slow.
        sourceToken = NotificationCenter.default.addObserver(
            forName: SourceDirection.didChange, object: nil, queue: .main
        ) { _ in
            Task { @MainActor in await reload(nil) }
        }
    }

    deinit {
        if let token { NotificationCenter.default.removeObserver(token) }
        if let sourceToken { NotificationCenter.default.removeObserver(sourceToken) }
    }
}
