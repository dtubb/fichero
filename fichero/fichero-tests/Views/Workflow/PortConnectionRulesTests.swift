@testable import Fichero
import XCTest

/// #4477: the canvas DERIVES edge legality from the engine's served table.
///
/// The old `canConnect` carried a hand-written five-conversion table; the
/// engine accepted one of them, so edges drew fine, saved fine, and died at
/// RUN time with "Invalid connection". These tests pin the derived rule:
/// same-type and "any" always; beyond that, ONLY what the engine served; and
/// an unloaded (empty) table is strict — it can never permit an edge the
/// engine would refuse.
final class PortConnectionRulesTests: XCTestCase {

    /// The engine's table as served today (workflows/validation.py
    /// PORT_CONVERSIONS → GET /api/workflows/tools `conversions`). If the
    /// engine adds a conversion this constant is NOT edited to match by hand
    /// — the canvas reads the served value; this fixture exists only to
    /// exercise the lookup.
    private let engineTable: [String: Set<String>] = ["files": ["file"]]

    func testSameTypeAndAnyAlwaysConnect() {
        XCTAssertTrue(PortConnectionRules.canConnect(
            outputType: "text", inputType: "text", conversions: [:]))
        XCTAssertTrue(PortConnectionRules.canConnect(
            outputType: "image", inputType: "any", conversions: [:]))
        XCTAssertTrue(PortConnectionRules.canConnect(
            outputType: "any", inputType: "files", conversions: [:]))
    }

    func testOnlyServedConversionsConnect() {
        XCTAssertTrue(PortConnectionRules.canConnect(
            outputType: "files", inputType: "file", conversions: engineTable))
        // The five conversions the old hand-written table invented — every
        // one is engine-rejected and must not connect.
        for (source, target) in [
            ("json", "text"), ("array", "json"), ("array", "text"),
            ("file", "files"), ("image", "file"), ("image", "files")
        ] {
            XCTAssertFalse(
                PortConnectionRules.canConnect(
                    outputType: source, inputType: target, conversions: engineTable),
                "\(source) -> \(target) is engine-rejected; permitting it " +
                "recreates the draw-fine-save-fine-die-at-run defect"
            )
        }
    }

    func testEmptyTableIsStrictNotPermissive() {
        // Before tools load the table is empty. Strict is safe: the canvas
        // may temporarily refuse a legal edge, but it can never permit an
        // edge the engine refuses — the failure mode that was live.
        XCTAssertFalse(PortConnectionRules.canConnect(
            outputType: "files", inputType: "file", conversions: [:]))
    }

    func testServedTableIsHonouredVerbatim() {
        // If the engine grows a conversion, the canvas follows with no code
        // change — that is the whole point of deriving.
        let grown: [String: Set<String>] = ["files": ["file"], "array": ["json"]]
        XCTAssertTrue(PortConnectionRules.canConnect(
            outputType: "array", inputType: "json", conversions: grown))
    }
}
