import XCTest

/// #4388 — the entity/SVO inspector detail rendered its canonical-name
/// headline as a 32pt custom serif face (`.system(size: 32, weight: .bold,
/// design: .serif)`), inconsistent with the semantic-font convention every
/// other surface in the app follows.
final class EntityDigestViewFontTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testCanonicalNameHeadlineUsesASemanticFontNotAFixedSerifSize() throws {
        let source = try Self.appSource("Views/Inspector/Knowledge/EntityDigestView.swift")
        XCTAssertFalse(
            source.contains(".system(size: 32, weight: .bold, design: .serif)"),
            "the reported fixed-size custom serif headline must not reappear"
        )
        // #4896: biographySection moved out of this file, so it can no longer
        // bound headerSection's scope — bound on headerSection's OWN closing
        // brace instead (the "\n    }" body-boundary pattern this codebase
        // already uses elsewhere), which survives whatever comes after it.
        let start = try XCTUnwrap(source.range(of: "private var headerSection: some View {"))
        let bodyEnd = try XCTUnwrap(source.range(of: "\n    }", range: start.upperBound..<source.endIndex))
        let headerSection = source[start.upperBound..<bodyEnd.lowerBound]
        XCTAssertTrue(headerSection.contains(".font(.title)"))
    }
}
