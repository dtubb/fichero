@testable import Fichero
import XCTest

final class LibraryImageViewTests: XCTestCase {
    func testLibraryImageLoadKeyIncludesDocumentAndImageType() {
        let thumbnail = LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail)
        let display = LibraryImageLoadKey(documentId: "doc-1", imageType: .display)
        let otherDocument = LibraryImageLoadKey(documentId: "doc-2", imageType: .thumbnail)

        XCTAssertEqual(thumbnail, LibraryImageLoadKey(documentId: "doc-1", imageType: .thumbnail))
        XCTAssertNotEqual(thumbnail, display)
        XCTAssertNotEqual(thumbnail, otherDocument)
    }
}
