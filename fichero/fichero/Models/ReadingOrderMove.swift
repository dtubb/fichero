import Foundation

/// A drag in a reading-order list, turned into the ONE engine call that performs it
/// (`source.editor.reorder`, #4941).
///
/// `reading_order.place` moves an entry that is already in the order — one row, one
/// audited action, its position the midpoint between its new neighbours so a move in a
/// thousand-entry flow touches one row. What it needs is `after_entry_id`: the entry the
/// moved one should FOLLOW, or none for the start of its level. A list UI speaks in
/// target indices, so the whole job of this type is the translation, and the
/// translation is an off-by-one waiting to happen: the neighbour is found in the list
/// WITH THE MOVED ENTRY TAKEN OUT, not in the list as drawn.
///
/// Pure, like `SegmentEditCommand`: the rule lives where a test can reach it.
enum ReadingOrderMove {
    /// One entry of one level of an order, as the list shows it.
    struct Entry: Equatable {
        let entryId: String
        let segmentId: String
        let version: Int
    }

    /// The `reading_order.place` request to send.
    struct Place: Equatable {
        let orderId: String
        let segmentId: String
        /// `nil` means the start of the level — which is a real answer, not a missing one.
        let afterEntryId: String?
        let expectedVersion: Int
    }

    enum Refusal: Error, Equatable {
        /// The segment being dragged is not in this level of the order. A drag in a list
        /// only moves what is there; inserting a new segment is a different verb, and
        /// letting a move quietly become an insert would add a line to a reading the
        /// person thought they were only rearranging.
        case notInThisOrder
        /// The target is outside the list.
        case targetOutOfRange
        /// Dropped where it already is. Sending it would write an audited action that
        /// changed nothing — noise in the record of how a reading was built.
        case alreadyThere
    }

    /// The call that moves `segmentId` to occupy `targetIndex` in the FINAL list.
    ///
    /// `targetIndex` is where the entry should end up, counted in the list as it will be
    /// after the move. That is the convention SwiftUI's `onMove` does NOT use (it reports
    /// an offset into the list as drawn, before removal), so a caller adapting `onMove`
    /// converts once, at the edge, rather than this type accepting both and guessing.
    static func place(
        orderId: String,
        entries: [Entry],
        moving segmentId: String,
        to targetIndex: Int
    ) -> Result<Place, Refusal> {
        guard let from = entries.firstIndex(where: { $0.segmentId == segmentId }) else {
            return .failure(.notInThisOrder)
        }
        guard targetIndex >= 0, targetIndex < entries.count else {
            return .failure(.targetOutOfRange)
        }
        guard targetIndex != from else { return .failure(.alreadyThere) }

        // The neighbour is found in the list WITHOUT the moved entry. Measuring it in the
        // list as drawn is the classic mistake: moving an entry DOWN would then land it
        // one place too far, because every index after it shifts up by one once it leaves.
        var remaining = entries
        let moved = remaining.remove(at: from)
        let after = targetIndex == 0 ? nil : remaining[targetIndex - 1].entryId

        return .success(Place(
            orderId: orderId,
            segmentId: moved.segmentId,
            afterEntryId: after,
            expectedVersion: moved.version
        ))
    }

    /// A KEYBOARD move: the same one call as a drag (ruled 2026-09-27, Q5: reordering by
    /// drag-and-drop AND by keys, with one behaviour in the Reader, the Inspector and the
    /// Segments pane -- one implementation, never three).
    enum Step: Equatable {
        /// One place earlier or later (⌥⌘↑ / ⌥⌘↓).
        case up, down
        /// To the start or the end of its level.
        case toStart, toEnd
    }

    /// The call a key press makes. Pressing up on the first entry is `alreadyThere`, never a
    /// wrap to the end: a key that sends the first line of a page to its last would be a
    /// surprise nobody asked for.
    static func place(
        orderId: String,
        entries: [Entry],
        moving segmentId: String,
        step: Step
    ) -> Result<Place, Refusal> {
        guard let from = entries.firstIndex(where: { $0.segmentId == segmentId }) else {
            return .failure(.notInThisOrder)
        }
        let target: Int
        switch step {
        case .up: target = max(from - 1, 0)
        case .down: target = min(from + 1, entries.count - 1)
        case .toStart: target = 0
        case .toEnd: target = entries.count - 1
        }
        return place(orderId: orderId, entries: entries, moving: segmentId, to: target)
    }

    /// SwiftUI's `onMove(fromOffsets:toOffset:)` for a single row, converted to the
    /// final-list index `place` takes. `toOffset` is an insertion point in the list AS
    /// DRAWN, so moving down lands one earlier once the row has left.
    static func finalIndex(fromOffset: Int, toOffset: Int) -> Int {
        toOffset > fromOffset ? toOffset - 1 : toOffset
    }
}
