import XCTest

/// #4388 — the entity/SVO inspector detail rendered its canonical-name
/// headline as a 32pt custom serif face (`.system(size: 32, weight: .bold,
/// design: .serif)`), inconsistent with the semantic-font convention every
/// other surface in the app follows.
final class EntityDigestViewFontTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testCanonicalNameHeadlineUsesASemanticFontNotAFixedSerifSize() throws {
        let source = try Self.appSource("Views/Inspector/Knowledge/EntityDigestView.swift")
        XCTAssertFalse(
            source.contains(".system(size: 32, weight: .bold, design: .serif)"),
            "the reported fixed-size custom serif headline must not reappear"
        )
        let headerSection = source
            .components(separatedBy: "private var headerSection: some View {")[1]
            .components(separatedBy: "\n    private var biographySection")[0]
        XCTAssertTrue(headerSection.contains(".font(.title)"))
    }
}
