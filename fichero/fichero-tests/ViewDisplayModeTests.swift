import XCTest

@testable import Fichero

/// Coverage for the Canvas & Space view-mode enum (#3081): the settled `.canvas`
/// / `.space` vocabulary and the deliberate absence of legacy-rawValue migration.
/// The library data isn't in production use, so the enum starts fresh — old
/// persisted strings decode to nil rather than being folded (Daniel, 2026-07-05).
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
        // icon/list/table/canvas/space — workspace is offered separately behind
        // its feature gate, so it is not in the base selectable set (#3081).
        XCTAssertEqual(ViewDisplayMode.selectableCases, [.icon, .list, .table, .canvas, .space])
        XCTAssertFalse(ViewDisplayMode.selectableCases.contains(.workspace))
    }

    func testAllCasesNoLongerIncludeRetiredAliases() {
        // The dead decode-only aliases are gone from the case list entirely.
        XCTAssertEqual(ViewDisplayMode.allCases, [.icon, .list, .table, .canvas, .space, .workspace])
    }

    func testLabels() {
        XCTAssertEqual(ViewDisplayMode.canvas.label, "Canvas")
        XCTAssertEqual(ViewDisplayMode.space.label, "Space")
        XCTAssertEqual(ViewDisplayMode.table.label, "Columns")
    }
}
