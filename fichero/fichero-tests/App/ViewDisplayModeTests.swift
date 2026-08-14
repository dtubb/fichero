import XCTest

@testable import Fichero

/// Coverage for the Canvas & Space view-mode enum (#3081): the settled `.canvas`
/// / `.space` vocabulary and the deliberate absence of legacy-rawValue migration.
/// The library data isn't in production use, so the enum starts fresh — old
/// persisted strings decode to nil rather than being folded (the user, 2026-07-05).
final class ViewDisplayModeTests: XCTestCase {

    // MARK: - No back-compat migration (clean start, no real data)

    func testLegacyRawValuesNoLongerDecode() {
        // "Map"/"Spatial"/"RealityKit" were the old view-mode strings. With the
        // back-compat shim removed they are unknown rawValues → nil (reset to
        // default), NOT silently folded onto .canvas.
        XCTAssertNil(ViewDisplayMode(rawValue: "Map"))
        XCTAssertNil(ViewDisplayMode(rawValue: "Spatial"))
        XCTAssertNil(ViewDisplayMode(rawValue: "RealityKit"))
    }

    // MARK: - Canonical decode

    func testCanonicalRawValuesDecode() {
        XCTAssertEqual(ViewDisplayMode(rawValue: "Icon"), .icon)
        XCTAssertEqual(ViewDisplayMode(rawValue: "List"), .list)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Table"), .table)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Canvas"), .canvas)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Space"), .space)
        XCTAssertEqual(ViewDisplayMode(rawValue: "Workspace"), .workspace)
    }

    func testUnknownRawValueIsNil() {
        XCTAssertNil(ViewDisplayMode(rawValue: "Nope"))
        XCTAssertNil(ViewDisplayMode(rawValue: ""))
    }

    // MARK: - Selectable set + labels

    func testSelectableCasesAreTheCoherentSet() {
        // icon/list/table/columns/canvas/space — workspace is offered
        // separately behind its feature gate, so it is not in the base
        // selectable set (#3081; columns added by #4160 step 4).
        // The dataset renderers are each a top-level mode (Daniel 2026-08-14,
        // superseding the combined "Data" mode of 29090f32f).
        XCTAssertEqual(
            ViewDisplayMode.selectableCases,
            [.icon, .list, .table, .columns, .cards, .timeline, .calendar, .geoMap, .canvas, .space]
        )
        XCTAssertFalse(ViewDisplayMode.selectableCases.contains(.workspace))
    }

    func testAllCasesNoLongerIncludeRetiredAliases() {
        // The dead decode-only aliases are gone from the case list entirely.
        XCTAssertEqual(
            ViewDisplayMode.allCases,
            [.icon, .list, .table, .canvas, .space, .columns,
             .cards, .timeline, .calendar, .geoMap, .workspace]
        )
    }

    func testLabels() {
        XCTAssertEqual(ViewDisplayMode.canvas.label, "Canvas")
        XCTAssertEqual(ViewDisplayMode.space.label, "Space")
        // #4160 step 4: a REAL Miller-columns mode exists, so the table
        // reverts to its honest name — two "Columns" would mislead.
        XCTAssertEqual(ViewDisplayMode.table.label, "Table")
        XCTAssertEqual(ViewDisplayMode.columns.label, "Columns")
    }
}
