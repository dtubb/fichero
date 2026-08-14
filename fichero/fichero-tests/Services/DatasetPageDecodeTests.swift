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
         "attributes": {"date": "1942-01-04"}},
        {"id": "img1", "name": "page.png", "prototype_key": null,
         "node_kind": null, "doc_type": "file", "attributes": {}}
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
        XCTAssertEqual(page.bins.map(\.bin), ["1942-02-09"], "bins re-derive from the new date")
        XCTAssertEqual(page.total, 2, "totals and untouched rows survive")
        // An edit to a row that is not on the page is a no-op, never a crash.
        store.applyLocalEdit(rowId: "ghost", attr: "date", value: "1942-03-01")
        XCTAssertEqual(store.page?.rows.count, 2)
    }
}
