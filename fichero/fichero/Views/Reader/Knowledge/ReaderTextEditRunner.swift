import Foundation

/// One Reader page message as ONE audited action (#5154, 13b) -- what `applyTextEdit` runs, apart
/// from the web view so the joint test can feed it the page's OWN posted messages and see the requests
/// (`ImportedPageDrawsItsBoxesTests.testTheServedPagesOwnMessagesBecomeTheRequestsTheEngineTakes`).
/// Answers the script that tells the page how it went, or nil when there is nothing to say.
@MainActor
struct ReaderTextEditRunner {
    let actionsService: ActionsService
    let segmentService: SegmentService
    let undoManager: UndoManager?
    /// Re-reads the page's text on screen (the coordinator's web view); a no-op in a test.
    let refreshPage: @MainActor (String) async -> Void

    func apply(_ edit: ReaderTextEdit.Message) async -> String? {
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
                try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                    call, documentId: pageId, actionName: "Join Lines", undoManager: undoManager,
                    afterChange: { await refreshPage(pageId) }
                )
            }
        } catch APIError.httpError(409, _) {
            // Stale (#5001): another reading counts now. Nothing was written; tell the page what counts
            // so it keeps the typed words and offers Keep Mine / Take Theirs / Compare. No refresh. A
            // split or join refused as stale has no typed words: a plain refusal.
            return await ReaderTextEdit.staleAnswer(to: edit, readings: segmentService)
                ?? ReaderTextEdit.committedScript(pageId: pageId, segmentId: edit.segmentId, reason: "stale")
        } catch {
            reason = String(describing: error)
        }
        return ReaderTextEdit.committedScript(
            pageId: pageId, segmentId: edit.segmentId, reason: reason, representationId: made
        )
    }
}
