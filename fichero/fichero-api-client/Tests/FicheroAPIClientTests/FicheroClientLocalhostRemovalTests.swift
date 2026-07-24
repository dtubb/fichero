import XCTest
@testable import FicheroAPIClient

final class FicheroClientLocalhostRemovalTests: XCTestCase {
    func testStaticLocalhostHelperIsRemovedFromPublicSource() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceURL = packageRoot
            .appendingPathComponent("Sources/FicheroAPIClient/FicheroClient.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        XCTAssertFalse(
            source.contains("static var localhost"),
            "FicheroClient.localhost must stay deleted so callers cannot bypass transportMode."
        )
        XCTAssertFalse(
            source.contains("static let localhost"),
            "FicheroClient.localhost must stay deleted so callers cannot bypass transportMode."
        )
    }
}
