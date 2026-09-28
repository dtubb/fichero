@testable import Fichero
import Testing

/// `source.editor.reorder` (#4941): a drag in a reading-order list becomes ONE
/// `reading_order.place`.
///
/// The translation from "target index" to "the entry this one follows" is an
/// off-by-one waiting to happen — the neighbour is found in the list with the moved
/// entry taken OUT. These tests are mostly about that, in both directions, because a
/// reorder that lands one place off is a reading of the page somebody did not make.
struct ReadingOrderMoveTests {

    private let entries: [ReadingOrderMove.Entry] = [
        .init(entryId: "e-a", segmentId: "s-a", version: 1),
        .init(entryId: "e-b", segmentId: "s-b", version: 2),
        .init(entryId: "e-c", segmentId: "s-c", version: 3),
        .init(entryId: "e-d", segmentId: "s-d", version: 4)
    ]

    private func place(_ segment: String, to index: Int) -> Result<ReadingOrderMove.Place, ReadingOrderMove.Refusal> {
        ReadingOrderMove.place(orderId: "o-1", entries: entries, moving: segment, to: index)
    }

    @Test("moving UP lands after the entry now before the target")
    func movingUp() throws {
        // a b c d  ->  move d to index 1  ->  a d b c : d follows a.
        let result = try place("s-d", to: 1).get()

        #expect(result.afterEntryId == "e-a")
        #expect(result.segmentId == "s-d")
        #expect(result.expectedVersion == 4)
    }

    @Test("moving DOWN is measured with the moved entry taken out")
    func movingDown() throws {
        // a b c d  ->  move a to index 2  ->  b c a d : a follows c.
        // Measured in the list AS DRAWN it would follow d — one place too far, because
        // every index after it shifts up once it leaves.
        let result = try place("s-a", to: 2).get()

        #expect(result.afterEntryId == "e-c")
    }

    @Test("moving to the very start follows nothing")
    func movingToStart() throws {
        // nil is a real answer — the start of the level — not a missing one.
        let result = try place("s-c", to: 0).get()

        #expect(result.afterEntryId == nil)
    }

    @Test("moving to the very end follows the last remaining entry")
    func movingToEnd() throws {
        // a b c d  ->  move a to index 3  ->  b c d a : a follows d.
        let result = try place("s-a", to: 3).get()

        #expect(result.afterEntryId == "e-d")
    }

    @Test("dropping an entry where it already is sends nothing")
    func droppingInPlace() {
        // An audited action that changed nothing is noise in the record of how a reading
        // was built.
        #expect(place("s-b", to: 1) == .failure(.alreadyThere))
    }

    @Test("a segment not in this level is not quietly inserted")
    func notInTheOrder() {
        // A drag in a list only moves what is there. A move that became an insert would
        // add a line to a reading the person thought they were only rearranging.
        #expect(place("s-zzz", to: 0) == .failure(.notInThisOrder))
    }

    @Test("a target outside the list is refused")
    func outOfRange() {
        #expect(place("s-a", to: 4) == .failure(.targetOutOfRange))
        #expect(place("s-a", to: -1) == .failure(.targetOutOfRange))
    }

    @Test("SwiftUI's onMove offsets convert to the final index once, at the edge")
    func onMoveConversion() {
        // onMove reports an insertion point in the list AS DRAWN. Moving row 0 below row 2
        // arrives as toOffset 3 and must land at final index 2.
        #expect(ReadingOrderMove.finalIndex(fromOffset: 0, toOffset: 3) == 2)
        // Moving up needs no correction.
        #expect(ReadingOrderMove.finalIndex(fromOffset: 3, toOffset: 1) == 1)
        // And the round trip from an onMove gesture to a place call agrees with the
        // direct index: row 0 dragged below row 2 follows c.
        let final = ReadingOrderMove.finalIndex(fromOffset: 0, toOffset: 3)
        #expect((try? place("s-a", to: final).get())?.afterEntryId == "e-c")
    }

    // MARK: - Keys (ruled 2026-09-27, Q5): the same one call as a drag.

    private func step(_ segment: String, _ step: ReadingOrderMove.Step)
        -> Result<ReadingOrderMove.Place, ReadingOrderMove.Refusal> {
        ReadingOrderMove.place(orderId: "o-1", entries: entries, moving: segment, step: step)
    }

    @Test("a key moves one place, and is exactly the drag to that place")
    func keyUpAndDownAreOneStep() throws {
        #expect(try step("s-c", .upward).get() == place("s-c", to: 1).get())
        #expect(try step("s-b", .downward).get() == place("s-b", to: 2).get())
        // b up to the top follows nothing -- the start of the level is a real answer.
        #expect(try step("s-b", .upward).get().afterEntryId == nil)
    }

    @Test("to start and to end reach the ends of the level")
    func toStartAndToEnd() throws {
        #expect(try step("s-c", .toStart).get().afterEntryId == nil)
        // c to the end of a b c d: a b d c -- c follows d.
        #expect(try step("s-c", .toEnd).get().afterEntryId == "e-d")
    }

    /// Never a wrap: up on the first line or down on the last sends nothing.
    @Test("at an end the key refuses rather than wrapping round")
    func noWrap() {
        #expect(step("s-a", .upward) == .failure(.alreadyThere))
        #expect(step("s-d", .downward) == .failure(.alreadyThere))
        #expect(step("s-a", .toStart) == .failure(.alreadyThere))
        #expect(step("s-d", .toEnd) == .failure(.alreadyThere))
    }

    @Test("a segment not in the order is refused by a key as by a drag")
    func keyOnAStranger() {
        #expect(step("s-z", .downward) == .failure(.notInThisOrder))
    }
}
