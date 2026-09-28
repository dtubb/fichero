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
}
