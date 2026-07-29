@testable import Fichero
import XCTest

final class FicheroDocumentPackagePathsTests: XCTestCase {
    func testPackagePathsUseStablePackageChildren() {
        let document = FicheroDocument(libraryName: "Test")
        let paths = document.packagePaths(
            for: URL(fileURLWithPath: "/tmp/library.fichero", isDirectory: true)
        )

        XCTAssertEqual(paths.databasePath.lastPathComponent, "fichero.duckdb")
        XCTAssertEqual(paths.lanceDBPath.lastPathComponent, "lance")
        XCTAssertEqual(paths.storagePath.lastPathComponent, "storage")
        XCTAssertEqual(paths.filesPath.lastPathComponent, "files")
        XCTAssertTrue(paths.filesPath.path.hasPrefix("/tmp/library.fichero/"))
    }
}
