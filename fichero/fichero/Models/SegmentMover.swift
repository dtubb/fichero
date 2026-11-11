import CoreTransferable
import Foundation
import UniformTypeIdentifiers

/// Move lines into a region, or out to the page, from any surface (`source.editor.segment-verbs-are-the-same-everywhere`,
/// Step 1.25): a menu item, a drop on a region row, a key. ONE plan (`SegmentEdit.reparent`), ONE audited
/// `segment.reparent` call (one ⌘Z for the whole selection) and one runner, the way `SegmentDeleter` does Delete.
@MainActor
enum SegmentMover {
    static let actionName = "Move Lines"

    /// The regions `ids` could move into: every other region of the page, in the page's order, minus any the selection
    /// itself holds. Uses the one rule `OrderDrop.accepted` (a segment goes only into one exactly a level coarser).
    static func targets(for ids: [String], in segments: [Segment]) -> [Segment] {
        guard !ids.isEmpty else { return [] }
        return segments.filter { region in
            region.kind == "region" && !OrderDrop.accepted(ids, into: region, in: segments).isEmpty
                && OrderDrop.accepted(ids, into: region, in: segments).count == ids.count
        }
    }

    /// Whether any of `ids` sits in a region now, so "Lift Out of Region" means something.
    static func canLift(_ ids: [String], in segments: [Segment]) -> Bool {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return ids.contains { byId[$0]?.parentSegmentId != nil }
    }

    /// Why nothing was sent, in words.
    static func problem(_ refusal: SegmentEdit.Refusal) -> String {
        switch refusal {
        case .tooFew: "Select a line to move."
        case .versionUnknown: "These lines are not saved yet, so they cannot be moved."
        }
    }

    /// Move `segments` into `parent` (nil: out to the page): nil when it was sent, else why not, never silent.
    static func run(
        _ segments: [Segment], into parent: String?, documentId: String, store: SegmentStore,
        services: (actions: ActionsService?, steps: WindowSteps?)
    ) async -> String? {
        let (actionsService, steps) = services
        guard let actionsService else { return "This window cannot edit." }
        switch SegmentEdit.reparent(segments, into: parent) {
        case .failure(let refusal):
            return problem(refusal)
        case .success(let call):
            do {
                try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                    call, documentId: documentId, actionName: actionName, steps: steps
                )
                return nil
            } catch {
                return "The lines were not moved: \(error.localizedDescription)"
            }
        }
    }
}

/// What a drag of lines carries: their ids, for a drop onto a region row. Dragged out of the app it is the lines' text
/// (`source.editor.order-list-drags-out-and-into-a-workflow`), so the same drag drops into a document or the Desktop.
struct SegmentDrag: Codable, Transferable, Equatable {
    var ids: [String]
    var text: String

    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .segmentDrag)
        ProxyRepresentation(exporting: \.text)
    }
}

extension UTType {
    /// The app's own type for a drag of lines; private to the app, so no other app takes the ids for anything.
    static let segmentDrag = UTType(exportedAs: "app.fichero.fichero.segment-drag", conformingTo: .data)
}
