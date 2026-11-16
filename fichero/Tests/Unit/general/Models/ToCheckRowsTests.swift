@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// "What to check" on the Read card (`designer.how.what-to-check`): the engine's pages, least sure first, worded one row each.
@MainActor
struct ToCheckRowsTests {
    private func pages() throws -> [Components.Schemas.PageToCheck] {
        let json = #"[{"page_id":"p1","certainty":0.31,"lines_unsure":4,"lines":12},"#
            + #"{"page_id":"p2","certainty":0.58,"lines_unsure":1,"lines":1}]"#
        return try JSONDecoder().decode([Components.Schemas.PageToCheck].self, from: Data(json.utf8))
    }

    @Test("one row a page, in the engine's order, keyed by the page so one press opens it")
    func rows() throws {
        let rows = ActivityDetails.toCheckRows(try pages())
        #expect(rows.map(\.id) == ["p1", "p2"])
        #expect(rows[0].text == "1. 31% sure · 4 unsure of 12 lines")
        #expect(rows[1].text.hasSuffix("of 1 line"))
    }

    @Test("no pages, no rows")
    func none() {
        #expect(ActivityDetails.toCheckRows([]).isEmpty)
    }
}
