import Foundation

/// Delete lines from any surface (`source.editor.delete-selected-lines`): the Segments pane, the Reader's lines, the
/// Inspector and Page > Segments take the Preview's own path, so there is ONE plan (`SegmentEdit.delete`), ONE audited
/// `segment.delete` batch -- one audit id, so one ⌘Z for the whole selection -- and one runner. Never a second delete.
@MainActor
enum SegmentDeleter {
    static let actionName = "Delete Lines"

    /// The segments `ids` name, in the order given; an id the store does not hold is left out.
    static func segments(_ ids: [String], documentId: String, store: SegmentStore) -> [Segment] {
        let byId = Dictionary(
            store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }
        )
        return ids.compactMap { byId[$0] }
    }

    /// The ids the focused Source view's selection holds on this page (one selection across the surfaces, #5155).
    static func selectedIds(_ selection: RegionSelection?, documentId: String, store: SegmentStore) -> [String] {
        guard let selection else { return [] }
        return InspectorPath.selectedSegmentIds(selection: selection, documentId: documentId, store: store)
    }

    /// The lines a Delete on `row` means: the focused Source view's held selection only when it CONTAINS the row, else just
    /// the row (the person highlighted another one); no row names the held selection itself. The one rule every surface
    /// uses, so a Delete never reaches lines the person did not point at (## 1072). Pure, for the tests.
    static func ids(row: String?, held: [String]) -> [String] {
        guard let row else { return held }
        return held.contains(row) ? held : [row]
    }

    /// Why nothing was sent, in words.
    static func problem(_ refusal: SegmentEdit.Refusal) -> String {
        switch refusal {
        case .tooFew: "Select a line to delete."
        case .versionUnknown: "These lines are not saved yet, so they cannot be deleted."
        }
    }

    /// Delete `segments`: nil when it was sent, else why not (a refusal or the engine's answer), never silent.
    /// `selection` is cleared on success: its held positions mean nothing once the lines are gone.
    static func run(
        _ segments: [Segment], documentId: String, store: SegmentStore, actionsService: ActionsService?,
        steps: WindowSteps?, clearing selection: RegionSelection? = nil
    ) async -> String? {
        guard let actionsService else { return "This window cannot edit." }
        switch SegmentEdit.delete(segments) {
        case .failure(let refusal):
            return problem(refusal)
        case .success(let call):
            do {
                try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                    call, documentId: documentId, actionName: actionName, steps: steps
                )
                selection?.clear()
                return nil
            } catch {
                return "The lines were not deleted: \(error.localizedDescription)"
            }
        }
    }
}
