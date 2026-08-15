@testable import Fichero
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import XCTest

/// The dataset response decode against the ENGINE'S ACTUAL WIRE JSON
/// (captured live 2026-08-14 while diagnosing "0 items" over a folder of
/// diary entries). The open-schema payload arrives through
/// OpenAPIObjectContainer, whose number bridging is not guaranteed to be
/// `Int` — the decode must survive whatever it produces.
@MainActor
final class DatasetPageDecodeTests: XCTestCase {
    private static let wireJSON = """
    {
      "total": 2,
      "offset": 0,
      "rows": [
        {"id": "e1", "name": "1942-01-04", "prototype_key": "diary_entry",
         "node_kind": "entry", "doc_type": "file",
         "attributes": {"date": "1942-01-04"},
         "excerpt": "Rained all day."},
        {"id": "img1", "name": "page.png", "prototype_key": null,
         "node_kind": null, "doc_type": "file", "attributes": {},
         "date_original": "Jan. 8th 1942", "date_iso": "1942-01-08"}
      ],
      "defaults_by_prototype": {
        "diary_entry": {"date": {"type": "date", "role": "date"}}
      },
      "bins": [{"bin": "1942-01-04", "count": 1}],
      "facets": {"weather": [{"value": "fair", "count": 1}]}
    }
    """

    private func decodeContainer() throws -> [String: (any Sendable)?] {
        let container = try JSONDecoder().decode(
            OpenAPIObjectContainer.self,
            from: Data(Self.wireJSON.utf8)
        )
        return container.value
    }

    func testWirePayloadDecodesRowsTotalsAndAggregates() throws {
        let page = DocumentService.datasetPage(from: try decodeContainer())

        XCTAssertEqual(page.total, 2, "total must survive the container's number bridging")
        XCTAssertEqual(page.rows.map(\.id), ["e1", "img1"])
        XCTAssertEqual(page.rows[0].prototypeKey, "diary_entry")
        XCTAssertEqual(page.rows[0].attributes["date"] as? String, "1942-01-04")
        XCTAssertEqual(page.rows[0].excerpt, "Rained all day.")
        XCTAssertNil(page.rows[1].excerpt, "absent excerpt decodes to nil, not empty text")
        // The document's OWN date (Extract Dates) rides the row.
        XCTAssertEqual(page.rows[1].dateOriginal, "Jan. 8th 1942")
        XCTAssertEqual(page.rows[1].dateIso, "1942-01-08")
        XCTAssertNil(page.rows[0].dateIso)
        XCTAssertEqual(page.bins.first?.count, 1)
        XCTAssertEqual(page.facets["weather"]?.first?.count, 1)
        // The defaults sidecar carries the typed declaration the renderers
        // derive roles from.
        let declaration = page.defaultsByPrototype["diary_entry"]?["date"]
            as? [String: (any Sendable)?]
        XCTAssertEqual(declaration?["role"] as? String, "date")
    }

    func testEffectiveValueOverlaysDefaults() throws {
        let page = DocumentService.datasetPage(from: try decodeContainer())
        let entry = page.rows[0]
        XCTAssertEqual(
            page.effectiveValue("date", of: entry) as? String, "1942-01-04"
        )
    }

    /// Update-in-place (project rule: no wholesale re-render): editing one
    /// row's date replaces THAT row and re-derives the day bins locally, so
    /// the calendar moves the entry without a reload.
    func testApplyLocalEditMovesTheRowAndRebins() throws {
        let store = DatasetModeStore()
        store.page = DocumentService.datasetPage(from: try decodeContainer())
        store.attributeForRole = ["date": "date"]

        store.applyLocalEdit(rowId: "e1", attr: "date", value: "1942-02-09")

        let page = try XCTUnwrap(store.page)
        XCTAssertEqual(page.rows.map(\.id), ["e1", "img1"], "only the row changed, in place")
        XCTAssertEqual(page.rows[0].attributes["date"] as? String, "1942-02-09")
        // Bins re-derive from EVERY date source: the edited attribute AND
        // img1's own extracted ISO date.
        XCTAssertEqual(page.bins.map(\.bin), ["1942-01-08", "1942-02-09"])
        XCTAssertEqual(page.total, 2, "totals and untouched rows survive")
        // An edit to a row that is not on the page is a no-op, never a crash.
        store.applyLocalEdit(rowId: "ghost", attr: "date", value: "1942-03-01")
        XCTAssertEqual(store.page?.rows.count, 2)
    }

    /// Extract Dates writes date COLUMNS, not attributes — a store with no
    /// date-role attribute still has a date source, groups by the rows' own
    /// ISO dates, and derives day bins locally.
    func testOwnDocumentDatesDriveGroupingAndLocalBins() throws {
        let store = DatasetModeStore()
        var page = DocumentService.datasetPage(from: try decodeContainer())
        // No date-role declaration: strip the sidecar the fixture carries.
        page = DatasetPage(
            total: page.total, offset: page.offset, rows: page.rows,
            defaultsByPrototype: [:], bins: [], facets: [:]
        )
        store.page = DatasetModeStore.withLocalDayBins(page, dateOf: { $0.dateIso })
        store.attributeForRole = [:]

        XCTAssertTrue(store.hasDateSource, "a row's own ISO date IS a date source")
        XCTAssertEqual(store.dateValue(of: page.rows[1]), "1942-01-08")
        XCTAssertEqual(store.page?.bins.map(\.bin), ["1942-01-08"])
        let groups = store.rowsByMonth()
        XCTAssertEqual(groups.first?.month, "1942-01")
        XCTAssertTrue(groups.first?.rows.contains(where: { $0.id == "img1" }) == true)
    }

    /// The grid's header sort: numeric when both sides parse, lexical
    /// otherwise, and missing values last in BOTH directions.
    func testGridComparatorNumericLexicalAndNilLast() {
        func row(_ id: String, _ value: (any Sendable)?) -> DatasetPage.Row {
            .init(id: id, name: id, prototypeKey: nil, attributes: ["n": value])
        }
        var comparator = DatasetAttributeComparator(attr: "n")
        // Numeric: "9" < "10" (lexical would invert it).
        XCTAssertEqual(comparator.compare(row("a", "9"), row("b", "10")), .orderedAscending)
        // Lexical fallback when either side is not a number.
        XCTAssertEqual(comparator.compare(row("a", "fog"), row("b", "rain")), .orderedAscending)
        // Missing values last, forward…
        XCTAssertEqual(comparator.compare(row("a", nil), row("b", "1")), .orderedDescending)
        comparator.order = .reverse
        // …and still last when the column is flipped.
        XCTAssertEqual(comparator.compare(row("a", nil), row("b", "1")), .orderedDescending)
        XCTAssertEqual(comparator.compare(row("a", "9"), row("b", "10")), .orderedDescending)
    }
}
