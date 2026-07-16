@testable import Fichero
import XCTest

@MainActor
final class LibraryRestoreReadinessTests: XCTestCase {
    private let libraryManager = LibraryManager.shared
    private var tempDirectory: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        libraryManager.openLibraries = []
        libraryManager.backendIsReady = false
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("LibraryRestoreReadinessTests")
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        libraryManager.openLibraries = []
        libraryManager.backendIsReady = false
        try? FileManager.default.removeItem(at: tempDirectory)
        try super.tearDownWithError()
    }

    func testSavedLibrariesWaitForBackendReadiness() throws {
        let defaults = UserDefaults.standard
        let originalPaths = defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey)
        let originalNames = defaults.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey)
        defer {
            if let originalPaths {
                defaults.set(originalPaths, forKey: LibraryManager.openLibraryPathsKey)
            } else {
                defaults.removeObject(forKey: LibraryManager.openLibraryPathsKey)
            }
            if let originalNames {
                defaults.set(originalNames, forKey: LibraryManager.libraryDisplayNamesByPathKey)
            } else {
                defaults.removeObject(forKey: LibraryManager.libraryDisplayNamesByPathKey)
            }
        }

        let savedLibrary = tempDirectory.appendingPathComponent("Restored.fichero", isDirectory: true)
        try FileManager.default.createDirectory(at: savedLibrary, withIntermediateDirectories: true)
        defaults.set([savedLibrary.path], forKey: LibraryManager.openLibraryPathsKey)

        libraryManager.restoreSavedLibraries()

        XCTAssertTrue(
            libraryManager.openLibraries.isEmpty,
            "Saved-library restoration must not issue registry work before the backend is ready"
        )

        libraryManager.backendIsReady = true
        libraryManager.restoreSavedLibraries()

        XCTAssertEqual(libraryManager.openLibraries.map(\.url), [savedLibrary])
    }
}
