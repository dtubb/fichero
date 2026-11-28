@testable import Fichero
import XCTest

/// The range a schema-driven number field offers comes from the keys the
/// engine serves. Tool schemas declare `minimum`/`maximum` (zoom, enhance,
/// economy HTR, …); the view read only `min`/`max`, so those fields were a
/// 0…1 slider whatever the tool declared.
/// spec: workflow-node-config `nodeconfig.fields.schema-driven.number-range`.
final class ConfigNumberBoundsTests: XCTestCase {

    func testReadsTheMinimumAndMaximumTheEngineServes() {
        // `zoom.scale` as served by workflows/tools/zoom.py.
        let schema: [String: AnyCodableValue] = [
            "type": .string("number"), "default": .double(2.0), "minimum": .double(1.0), "maximum": .double(6.0)
        ]
        XCTAssertEqual(ConfigNumberBounds.range(schema: schema), 1.0...6.0)
    }

    func testReadsTheShortKeysSomeToolsStillDeclare() {
        // `temperature` in workflows/tools/llm_base.py declares min/max as integers.
        let schema: [String: AnyCodableValue] = ["type": .string("number"), "min": .int(0), "max": .int(2)]
        XCTAssertEqual(ConfigNumberBounds.range(schema: schema), 0.0...2.0)
    }

    func testAFieldWithNoDeclaredRangeHasNone() {
        // `contrast` in registry_builtins.py: a default and no bounds. A slider
        // would have to invent a range the tool never declared.
        XCTAssertNil(ConfigNumberBounds.range(schema: ["type": .string("number"), "default": .double(1.2)]))
        XCTAssertNil(ConfigNumberBounds.range(schema: ["type": .string("number"), "minimum": .double(5)]))
        XCTAssertNil(ConfigNumberBounds.range(schema: ["type": .string("number"), "maximum": .double(5)]))
    }

    func testAnEmptyOrInvertedRangeHasNone() {
        // `ClosedRange` traps when the lower bound is above the upper one.
        XCTAssertNil(ConfigNumberBounds.range(schema: ["minimum": .double(5), "maximum": .double(1)]))
        XCTAssertNil(ConfigNumberBounds.range(schema: ["minimum": .double(3), "maximum": .double(3)]))
    }

    func testTheStepLetsADeclaredDefaultBeReached() {
        // overlap 0…0.3 defaults to 0.15; a 0.1 step could never land on it.
        XCTAssertEqual(ConfigNumberBounds.step(for: 0.0...0.3), 0.01)
        XCTAssertEqual(ConfigNumberBounds.step(for: 0.0...1.0), 0.01)
        XCTAssertEqual(ConfigNumberBounds.step(for: 0.0...2.0), 0.1)
        XCTAssertEqual(ConfigNumberBounds.step(for: 1.0...6.0), 0.1)
        XCTAssertEqual(ConfigNumberBounds.step(for: 0.0...100.0), 1.0)
    }

    func testTheShownValueHasTheStepsPrecision() {
        XCTAssertEqual(ConfigNumberBounds.label(0.15, step: 0.01), "0.15")
        XCTAssertEqual(ConfigNumberBounds.label(2.5, step: 0.1), "2.5")
        XCTAssertEqual(ConfigNumberBounds.label(40, step: 1.0), "40")
    }
}
