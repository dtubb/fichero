@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Prepare Images operation rows (`wide.prepare.four-operations-listed`, #5580): the rows come from the engine's listing in its
/// order; the person's switch is the whole answer `prepare_operations` and wins over the engine's defaults.
struct PrepareOperationsTests {
    private func operation(_ id: String, on: Bool) throws -> Components.Schemas.PrepareOperation {
        let json = #"{"id":"\#(id)","title":"\#(id.capitalized)","sentence":"does \#(id)","default":\#(on),"on":\#(on),"by_hand":false}"#
        return try JSONDecoder().decode(Components.Schemas.PrepareOperation.self, from: Data(json.utf8))
    }

    private func listing() throws -> [Components.Schemas.PrepareOperation] {
        [try operation("split", on: false), try operation("straighten", on: true), try operation("crop", on: true),
         try operation("clarity", on: false)]
    }

    @Test("with no answer the rows are the engine's, in its order")
    func rowsFollowTheListing() throws {
        let rows = PrepareOperationRows.rows(of: try listing(), answer: nil)
        #expect(rows.map(\.id) == ["split", "straighten", "crop", "clarity"])
        #expect(rows.map(\.isOn) == [false, true, true, false])
        #expect(rows[1].sentence == "does straighten")
    }

    @Test("the person's answer wins over the defaults")
    func theHandWins() throws {
        let rows = PrepareOperationRows.rows(of: try listing(), answer: .many(["clarity", "split"]))
        #expect(rows.map(\.isOn) == [true, false, false, true])
    }

    @Test("a first switch keeps the others as they were and the answer is the whole list in the engine's order")
    func switchingWritesTheWholeList() throws {
        let rows = PrepareOperationRows.rows(of: try listing(), answer: nil)
        #expect(PrepareOperationRows.answer(after: "clarity", to: true, rows: rows) == .many(["straighten", "crop", "clarity"]))
        #expect(PrepareOperationRows.answer(after: "crop", to: false, rows: rows) == .many(["straighten"]))
    }

    @Test("every operation off is said, not left blank")
    func everyOperationOff() throws {
        let rows = PrepareOperationRows.rows(of: try listing(), answer: .many([]))
        #expect(PrepareOperationRows.summary(of: rows) == "Every operation is off: Prepare Images runs nothing.")
        #expect(PrepareOperationRows.summary(of: PrepareOperationRows.rows(of: try listing(), answer: nil))
                == "Runs: straighten, crop.")
    }

    @Test("the rest of the suite is offered after the four, off until the person switches it on")
    func theRestOfTheSuiteFollows() throws {
        let listing = try ["split", "straighten", "crop", "clarity", "binarise", "flip"].map { try operation($0, on: ["straighten", "crop", "clarity"].contains($0)) }
        let rows = PrepareOperationRows.rows(of: listing, answer: nil)
        #expect(rows.map(\.id) == ["split", "straighten", "crop", "clarity", "binarise", "flip"])
        #expect(rows.suffix(2).allSatisfy { !$0.isOn })
        let after = PrepareOperationRows.answer(after: "flip", to: true, rows: rows)
        #expect(after == .many(["straighten", "crop", "clarity", "flip"]))
    }
}

@MainActor @Test("the page says how many folders answer for themselves, never their names")
func ownAnswersLine() {
    #expect(PrepareImagesCard.ownAnswersLine(count: 0) == nil)
    #expect(PrepareImagesCard.ownAnswersLine(count: 1) == "1 folder answers for itself")
    #expect(PrepareImagesCard.ownAnswersLine(count: 2) == "2 folders answer for themselves")
}
