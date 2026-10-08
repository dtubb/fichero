@testable import Fichero
import Testing

/// The Inspector's statements (5.7). What breaks without these: a claim shown without saying HOW it
/// points here (its own anchor or a supporting source), a machine's confidence dropped, or a mention
/// that opens a claim instead of its entity.
struct InspectorStatementsTests {
    @Test("claims first, each saying how it points here; then the entities mentioned")
    func rowsInWords() {
        let rows = InspectorStatements.rows(.init(
            claims: [
                .init(id: "c1", text: "Abraham begat Isaac", curationState: "unreviewed", confidence: 0.5, via: "anchor",
                      excerpt: "ܐܒܪܗܡ ܐܘܠܕ"),
                .init(id: "c2", text: "Isaac begat Jacob", curationState: "curated", confidence: 0.9, via: "support")
            ],
            mentions: [.init(id: "e1", name: "Abraham", entityType: "person", excerpt: "ܐܒܪܗܡ")]
        ))
        #expect(rows.map(\.title) == ["Abraham begat Isaac", "Isaac begat Jacob", "Abraham"])
        #expect(rows.map(\.isClaim) == [true, true, false])
        #expect(rows[0].detail == "unreviewed · confidence 50% · anchored here · “ܐܒܪܗܡ ܐܘܠܕ”")
        #expect(rows[1].detail == "curated · confidence 90% · a supporting source is here")
        #expect(rows[2].detail == "person · “ܐܒܪܗܡ”")
        #expect(Set(rows.map(\.id)).count == 3, "a claim and an entity with one id stay two rows")
    }

    // MARK: Corrected in place (#5602)

    private static let line = "En Istmina, Juan de Mosquera vecino"
    private static let juan = InspectorStatements.Mention(
        id: "e-juan", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan",
        sourceCharStart: 112, sourceCharEnd: 116, charStart: 12, charEnd: 16
    )

    private static func range(of words: String, in text: String) -> Range<String.Index> {
        text.firstRange(of: words) ?? text.startIndex..<text.startIndex
    }

    @Test("two marks of one entity on a line stay two rows; a person's mark says so")
    func marksAreRowsOfTheirOwn() {
        var again = Self.juan
        again.sourceCharStart = 140
        again.sourceCharEnd = 144
        again.correctedByPerson = true
        let rows = InspectorStatements.rows(.init(mentions: [Self.juan, again]))
        #expect(Set(rows.map(\.id)).count == 2)
        #expect(rows.map(\.corrected) == [false, true])
        #expect(rows.allSatisfy { $0.targetId == "e-juan" }, "each still opens its entity")
    }

    @Test("Fix the words: the words selected on the line become the mark's span in the page text")
    func respanFromTheLine() {
        let target = InspectorStatements.respanTarget(
            Self.juan, lineText: Self.line, selection: Self.range(of: "Juan de Mosquera", in: Self.line)
        )
        #expect(target?.start == 112)
        #expect(target?.end == 128)
    }

    @Test("Fix the words counts as the engine does: Unicode scalars, not UTF-16")
    func respanCountsScalars() {
        let line = "𝔄 Juan de Mosquera"   // 𝔄 is one scalar, two UTF-16 units
        let mention = InspectorStatements.Mention(
            id: "e-juan", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan",
            sourceCharStart: 50, sourceCharEnd: 54, charStart: 2, charEnd: 6
        )
        #expect(InspectorStatements.lineTextMatches(mention, lineText: line))
        let target = InspectorStatements.respanTarget(
            mention, lineText: line, selection: Self.range(of: "Juan de Mosquera", in: line)
        )
        #expect(target?.start == 50)
        #expect(target?.end == 66)
    }

    @Test("Fix the words is not offered, or sends nothing, when it cannot be right")
    func respanRefusals() {
        // The same words selected again: nothing moved.
        #expect(InspectorStatements.respanTarget(
            Self.juan, lineText: Self.line, selection: Self.range(of: "Juan", in: Self.line)) == nil)
        // A blank selection.
        #expect(InspectorStatements.respanTarget(
            Self.juan, lineText: Self.line, selection: Self.range(of: " ", in: Self.line)) == nil)
        // A line that is not the text the mark counts in (its words are not the mark's).
        let other = "Pedro de Mosquera, vecino de Istmina"
        #expect(!InspectorStatements.lineTextMatches(Self.juan, lineText: other))
        #expect(InspectorStatements.respanTarget(
            Self.juan, lineText: other, selection: Self.range(of: "Pedro", in: other)) == nil)
        // A mark with no page span.
        var spanless = Self.juan
        spanless.sourceCharStart = nil
        #expect(spanless.pageSpan == nil)
        #expect(!InspectorStatements.lineTextMatches(spanless, lineText: Self.line))
    }

    @Test("Change date takes a year, a month or a day, and nothing else")
    func claimDates() {
        #expect(InspectorStatements.claimDate(" 1650 ") == "1650")
        #expect(InspectorStatements.claimDate("1650-03") == "1650-03")
        #expect(InspectorStatements.claimDate("1650-03-01") == "1650-03-01")
        #expect(InspectorStatements.claimDate("") == nil)
        #expect(InspectorStatements.claimDate("March 1650") == nil)
        #expect(InspectorStatements.claimDate("1650-13") == nil)
        #expect(InspectorStatements.claimDate("1650-03-32") == nil)
    }
}
