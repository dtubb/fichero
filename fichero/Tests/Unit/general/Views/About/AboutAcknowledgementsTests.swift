import XCTest

@testable import Fichero

/// Coverage for the About window's acknowledgements MODEL
/// (`docs/contributor_manual/specs/ui/about.md` — `about.acknowledgements.*`).
/// Pure data assertions on `AboutAcknowledgements.entries`, `Acknowledgement`,
/// and `AckLayer`; no view, no bundle. Complements the URL/uniqueness checks in
/// `AboutInfoTests`.
final class AboutAcknowledgementsTests: XCTestCase {

    private var entries: [Acknowledgement] { AboutAcknowledgements.entries }

    /// The acknowledgement rows carry the stable a11y id `about.ack.<versionKey>`,
    /// so two entries MUST NOT share a version key or the identifiers collide and
    /// a UI test can't address the rows uniquely. (`about.acknowledgements.rows`)
    func testVersionKeysAreUniqueForStableAccessibilityIds() {
        let keys = entries.map(\.versionKey)
        XCTAssertEqual(Set(keys).count, keys.count, "duplicate versionKey → duplicate about.ack.* a11y id")
    }

    /// A `distribution` override becomes the (lowercased) version key so the LIVE
    /// version lookup keys off the pip/SPM name, not the display name.
    func testDistributionOverrideDrivesLowercasedVersionKey() {
        XCTAssertEqual(entry(named: "Model Context Protocol (MCP)").versionKey, "mcp")
        XCTAssertEqual(entry(named: "OpenCV").versionKey, "opencv-python-headless")
        XCTAssertEqual(entry(named: "MLX (mlx-lm, mlx-vlm, mlx-whisper)").versionKey, "mlx-lm")
    }

    /// Without a `distribution`, the version key is just the lowercased display name.
    func testDefaultVersionKeyIsLowercasedDisplayName() {
        XCTAssertEqual(entry(named: "FastAPI").versionKey, "fastapi")
        XCTAssertEqual(entry(named: "DuckDB").versionKey, "duckdb")
    }

    /// The sheet groups entries into three layers; every layer must be non-empty so
    /// no `Section` renders as a dangling header. (`about.acknowledgements.grouped`)
    func testEveryLayerIsPopulated() {
        for layer in AckLayer.allCases {
            XCTAssertFalse(
                entries.filter { $0.layer == layer }.isEmpty,
                "AckLayer.\(layer) has no acknowledgements — its Section would render empty"
            )
        }
    }

    /// The display order of the grouped credits is app → engine → on-device
    /// ("what the app is built on", top of the stack down). (`about.acknowledgements.layerOrder`)
    func testLayerDisplayOrder() {
        XCTAssertEqual(AckLayer.allCases, [.app, .engine, .onDevice])
    }

    private func entry(named name: String) -> Acknowledgement {
        guard let match = entries.first(where: { $0.name == name }) else {
            XCTFail("no acknowledgement named \(name)")
            return entries[0]
        }
        return match
    }
}
