import Foundation

/// Join Lines in the Same Row from any surface (`segment-editor.join-lines-in-the-same-row`): ask the engine which lines
/// share a row, say what it will do, send ONE audited `segment.join_rows` (one ⌘Z), say what it did. The notes go to
/// `note` (the window's segment notice), before and after.
@MainActor
struct SegmentRowJoiner {
    static let actionName = "Join Lines in the Same Row"

    let documentId: String
    let service: SegmentService
    let store: SegmentStore
    let actionsService: ActionsService
    let steps: WindowSteps?
    let windowState: WindowState?

    /// `segmentIds` nil: every line of the page. Nothing is thrown: a failure is said through `note`.
    func run(
        segmentIds: [String]?, note: @escaping (String?) -> Void, afterReread: @escaping @MainActor () async -> Void = {}
    ) async {
        let documentId = documentId, store = store, windowState = windowState
        do {
            let (rows, leftAlone) = try await service.joinRowsPreview(documentId: documentId, segmentIds: segmentIds)
            guard !rows.isEmpty else { return note(SegmentEdit.joinRowsNothing) }
            guard case .success(let call) = SegmentEdit.joinRows(rows, segments: store.segments(documentId: documentId)) else {
                return note(SegmentMover.problem(.versionUnknown))
            }
            note(SegmentEdit.joinRowsWillSay(rows: rows, leftAlone: leftAlone))
            // After each re-read (the join, its undo, its redo): each row's kept line, or its lines once undone.
            let reselect: @MainActor () async -> Void = {
                await afterReread()
                guard let windowState else { return }
                let live = Set(store.segments(documentId: documentId).map(\.id))
                windowState.pickInReader(
                    SegmentEdit.selectionAfterJoinRows(rows: rows, live: live), documentId: documentId, store: store
                )
            }
            try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                call, documentId: documentId, actionName: Self.actionName, steps: steps, afterChange: reselect
            )
            note(SegmentEdit.joinRowsDone(rows: rows, leftAlone: leftAlone))
        } catch {
            note("That did not happen: \(error.localizedDescription)")
        }
    }
}
