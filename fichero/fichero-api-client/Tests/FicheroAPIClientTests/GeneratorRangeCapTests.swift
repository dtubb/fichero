import Foundation
import XCTest

/// The swift-openapi-generator range is capped below 1.13.0 so every machine builds the same generated code.
///
/// spec: code-organization
/// behaviour: code-org.ratchet.generated-warnings-fixed-at-source
///
/// 1.13.0 writes `public import` at the head of every generated file and the protocol-only `Types.swift` then warns
/// `UnusedImportAccess` four times (apple/swift-openapi-generator#968, fix pending in #947). Lift the cap when #947 ships.
final class GeneratorRangeCapTests: XCTestCase {
    private var packageRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // FicheroAPIClientTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // package root
    }

    func testPackageSwiftCapsGeneratorBelow1_13() throws {
        let manifest = try String(contentsOf: packageRoot.appendingPathComponent("Package.swift"), encoding: .utf8)
        let line = try XCTUnwrap(
            manifest.split(separator: "\n").map(String.init).first {
                $0.contains("swift-openapi-generator") && $0.contains(".package(")
            },
            "Package.swift has no swift-openapi-generator dependency line"
        )
        XCTAssertTrue(line.contains("\"1.6.0\"..<\"1.13.0\""), "generator range must be capped below 1.13.0: \(line)")
        XCTAssertFalse(line.contains("from: \"1.6.0\""), "open-ended `from:` range lets Xcode resolve 1.13+: \(line)")
    }

    func testResolvedGeneratorPinIsBelow1_13() throws {
        let data = try Data(contentsOf: packageRoot.appendingPathComponent("Package.resolved"))
        let root = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let pins = try XCTUnwrap(root["pins"] as? [[String: Any]])
        let pin = try XCTUnwrap(pins.first { $0["identity"] as? String == "swift-openapi-generator" })
        let state = try XCTUnwrap(pin["state"] as? [String: Any])
        let version = try XCTUnwrap(state["version"] as? String)
        let parts = version.split(separator: ".").prefix(2).compactMap { Int($0) }
        XCTAssertEqual(parts.count, 2, "unparseable version \(version)")
        XCTAssertTrue(
            parts[0] < 1 || (parts[0] == 1 && parts[1] < 13),
            "pinned generator \(version) must be below 1.13.0"
        )
    }
}
