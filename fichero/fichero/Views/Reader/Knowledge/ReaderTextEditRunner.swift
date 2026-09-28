import Foundation

/// One Reader page message as ONE audited action (#5154, 13b) -- what `applyTextEdit` runs, apart
/// from the web view so the joint test can feed it the page's OWN posted messages and see the requests
/// (`ImportedPageDrawsItsBoxesTests.testTheServedPagesOwnMessagesBecomeTheRequestsTheEngineTakes`).
/// Answers the script that tells the page how it went, or nil when there is nothing to say.
@MainActor
struct ReaderTextEditRunner {
    /// What to tell the page, and -- when the write never reached the engine -- why, so the
    /// coordinator can tell the page the engine is out of reach and watch for its return.
    struct Answer {
        let script: String
        var unreachableReason: String?
        /// Why nothing was written, for a caller that is not the page (the Inspector's Edit…, #5201):
        /// nil when the edit landed; `staleProblem` when another reading counts now; else the reason.
        var problem: String?
    }

    nonisolated static let staleProblem = "stale"

    let actionsService: ActionsService
    let segmentService: SegmentService
    let undoManager: UndoManager?
    /// Re-reads the page's text on screen (the coordinator's web view); a no-op in a test.
    let refreshPage: @MainActor (String) async -> Void

    func apply(_ edit: ReaderTextEdit.Message) async -> Answer? {
        let store = SegmentStore.shared(for: segmentService)
        let pageId = edit.pageId
        let refreshPage = refreshPage
        let refresh: @MainActor () async -> Void = {
            await store.load(documentId: pageId, force: true)
            await refreshPage(pageId)
        }
        var reason: String?, made: String?  // why it was refused; the reading a typed run made
        do {
            switch edit {
            case .edited:
                guard let params = ReaderTextEdit.newReading(for: edit) else { return nil }
                made = try await AuditedAction.run(
                    "representation.create", params: params, actionName: "Typing", actionsService: actionsService,
                    undoManager: undoManager, afterChange: refresh
                ).resultId
            case .split(_, let id, _):
                // Fresh: a readingEdit posted just before the split changed the line's text and version.
                await store.load(documentId: pageId, force: true)
                guard let line = store.segments(documentId: pageId).first(where: { $0.id == id }) else {
                    throw SegmentEdit.Refusal.tooFew
                }
                let shown = try? await segmentService.readings(segmentId: id)
                let params = try ReaderTextEdit.split(
                    edit, of: line, shownText: shown?.countingContent(ofKind: "transcription")
                ).get()
                try await AuditedAction.run(
                    "segment.split", params: params, actionName: "Split Line", actionsService: actionsService,
                    undoManager: undoManager, afterChange: refresh
                )
            case .join:
                await store.load(documentId: pageId, force: true)
                let call = try ReaderTextEdit.join(edit, segments: store.segments(documentId: pageId)).get()
                // No afterChange: the runner posts `didChange`, which re-reads the Reader's page (#5171);
                // refreshing here too would read it twice.
                try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                    call, documentId: pageId, actionName: "Join Lines", undoManager: undoManager
                )
            }
        } catch let error where ReaderTextEdit.unreachableReason(error) != nil {
            return unreachable(edit, reason: ReaderTextEdit.unreachableReason(error) ?? "engine unreachable")
        } catch APIError.httpError(409, _) {
            // Stale (#5001): another reading counts now. Nothing was written; tell the page what counts
            // so it keeps the typed words and offers Keep Mine / Take Theirs / Compare. No refresh. A
            // split or join refused as stale has no typed words: a plain refusal.
            return Answer(
                script: await ReaderTextEdit.staleAnswer(to: edit, readings: segmentService)
                    ?? ReaderTextEdit.committedScript(pageId: pageId, segmentId: edit.segmentId, reason: "stale"),
                problem: Self.staleProblem
            )
        } catch {
            reason = String(describing: error)
        }
        return Answer(script: ReaderTextEdit.committedScript(
            pageId: pageId, segmentId: edit.segmentId, reason: reason, representationId: made
        ), problem: reason)
    }

    /// Out of reach (13b): nothing was written. A typed run goes back to held on the page; a split or
    /// join is a plain refusal. Either way the coordinator is told why, and says the engine is gone.
    private func unreachable(_ edit: ReaderTextEdit.Message, reason: String) -> Answer {
        let script = if case .edited = edit {
            ReaderTextEdit.unreachableScript(pageId: edit.pageId, segmentId: edit.segmentId, reason: reason)
        } else {
            ReaderTextEdit.committedScript(pageId: edit.pageId, segmentId: edit.segmentId, reason: reason)
        }
        return Answer(script: script, unreachableReason: reason, problem: reason)
    }
}
