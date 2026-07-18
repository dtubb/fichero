@testable import Fichero
import XCTest

final class FileProgressIdentityTests: XCTestCase {
    func testStableIdentityAndDisplayNamePreferPageMetadata() {
        let page = FileProgressIdentity(
            filePath: "/tmp/source.pdf",
            documentId: "doc-1",
            pageId: "page-2",
            displayName: "",
            sequence: 2
        )

        XCTAssertEqual(page.stableId, "page-2")
        XCTAssertEqual(page.leafDocumentId, "page-2")
        XCTAssertEqual(page.resolvedDisplayName, "Page 2")
    }

    func testDisplayNameFallsBackToFileName() {
        let file = FileProgressIdentity(
            filePath: "/tmp/source.pdf",
            documentId: nil,
            pageId: nil,
            displayName: nil,
            sequence: nil
        )

        XCTAssertEqual(file.stableId, "/tmp/source.pdf")
        XCTAssertNil(file.leafDocumentId)
        XCTAssertEqual(file.resolvedDisplayName, "source.pdf")
    }
}
