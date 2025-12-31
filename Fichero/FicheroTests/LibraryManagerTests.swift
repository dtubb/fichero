import XCTest
@testable import Fichero

@MainActor
final class LibraryManagerTests: XCTestCase {
    var libraryManager: LibraryManager!
    var tempDirectory: URL!

    override func setUp() async throws {
        try await super.setUp()

        // Get a clean instance for each test
        libraryManager = LibraryManager()

        // Create a temporary test directory
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroTests")
            .appendingPathComponent(UUID().uuidString)

        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        // Clean up temporary test directory
        if FileManager.default.fileExists(atPath: tempDirectory.path) {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        try await super.tearDown()
    }

    // MARK: - Library Creation Tests

    func testCreateNewLibrary() async throws {
        // When
        let library = libraryManager.createNewLibrary()

        // Then
        XCTAssertEqual(library.displayName, "Untitled", "First library should be named 'Untitled'")
        XCTAssertTrue(libraryManager.isTemporaryLibrary(library.url), "New library should be in temp directory")
        XCTAssertTrue(FileManager.default.fileExists(atPath: library.url.path), "Library package should exist on disk")
        XCTAssertEqual(libraryManager.openLibraries.count, 1, "Should have one open library")
        XCTAssertEqual(libraryManager.currentLibraryId, library.id, "Current library should be the new one")
    }

    func testCreateMultipleNewLibraries() async throws {
        // When
        let library1 = libraryManager.createNewLibrary()
        let library2 = libraryManager.createNewLibrary()
        let library3 = libraryManager.createNewLibrary()

        // Then
        XCTAssertEqual(library1.displayName, "Untitled", "First library should be 'Untitled'")
        XCTAssertEqual(library2.displayName, "Untitled 2", "Second library should be 'Untitled 2'")
        XCTAssertEqual(library3.displayName, "Untitled 3", "Third library should be 'Untitled 3'")
        XCTAssertEqual(libraryManager.openLibraries.count, 3, "Should have three open libraries")
        XCTAssertNotEqual(library1.id, library2.id, "Libraries should have different IDs")
        XCTAssertNotEqual(library2.id, library3.id, "Libraries should have different IDs")
    }

    func testLibraryHasPackageStructure() async throws {
        // When
        let library = libraryManager.createNewLibrary()

        // Then
        let contentsDir = library.url.appendingPathComponent("Contents")
        let infoPlist = contentsDir.appendingPathComponent("Info.plist")

        XCTAssertTrue(FileManager.default.fileExists(atPath: contentsDir.path), "Contents directory should exist")
        XCTAssertTrue(FileManager.default.fileExists(atPath: infoPlist.path), "Info.plist should exist")
    }

    // MARK: - Save Tests

    func testSaveLibraryPreservesID() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let originalID = library.id
        let saveURL = tempDirectory.appendingPathComponent("Test.fichero")

        // When
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // Then
        guard let savedLibrary = libraryManager.getLibrary(id: originalID) else {
            XCTFail("Library should still exist with same ID")
            return
        }

        XCTAssertEqual(savedLibrary.id, originalID, "Library ID should be preserved after save")
        XCTAssertEqual(savedLibrary.url, saveURL, "Library URL should be updated")
        XCTAssertEqual(savedLibrary.displayName, "Test", "Display name should match file name")
    }

    func testSaveLibraryMovesPackage() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let oldURL = library.url
        let saveURL = tempDirectory.appendingPathComponent("Saved.fichero")

        // When
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // Then
        XCTAssertTrue(FileManager.default.fileExists(atPath: saveURL.path), "Package should exist at new location")
        XCTAssertFalse(FileManager.default.fileExists(atPath: oldURL.path), "Old temp package should be moved (not copied)")
    }

    func testSaveLibraryPreservesAPIClient() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let originalAPIClient = library.apiClient
        let originalAPIClientID = ObjectIdentifier(originalAPIClient)
        let saveURL = tempDirectory.appendingPathComponent("Test.fichero")

        // When
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // Then
        guard let savedLibrary = libraryManager.getLibrary(id: library.id) else {
            XCTFail("Library should still exist")
            return
        }

        XCTAssertEqual(ObjectIdentifier(savedLibrary.apiClient), originalAPIClientID, "Should reuse same APIClient instance")
        XCTAssertEqual(savedLibrary.apiClient.currentLibraryPath, saveURL.path, "APIClient path should be updated")
    }

    func testSaveLibraryPreservesDocumentStore() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let originalDocumentStore = library.documentStore
        let originalStoreID = ObjectIdentifier(originalDocumentStore)
        let saveURL = tempDirectory.appendingPathComponent("Test.fichero")

        // When
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // Then
        guard let savedLibrary = libraryManager.getLibrary(id: library.id) else {
            XCTFail("Library should still exist")
            return
        }

        XCTAssertEqual(ObjectIdentifier(savedLibrary.documentStore), originalStoreID, "Should reuse same DocumentStore instance")
    }

    func testSaveNonexistentLibraryThrows() async throws {
        // Given
        let fakeID = UUID()
        let saveURL = tempDirectory.appendingPathComponent("Test.fichero")

        // When/Then
        XCTAssertThrowsError(try libraryManager.saveLibrary(fakeID, to: saveURL)) { error in
            XCTAssertTrue(error is LibraryError, "Should throw LibraryError")
        }
    }

    // MARK: - Temporary Library Detection Tests

    func testIsTemporaryLibrary() async throws {
        // Given
        let library = libraryManager.createNewLibrary()

        // When/Then
        XCTAssertTrue(libraryManager.isTemporaryLibrary(library.url), "New library should be temporary")
    }

    func testIsNotTemporaryLibraryAfterSave() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let saveURL = tempDirectory.appendingPathComponent("Saved.fichero")

        // When
        try libraryManager.saveLibrary(library.id, to: saveURL)
        guard let savedLibrary = libraryManager.getLibrary(id: library.id) else {
            XCTFail("Library should exist")
            return
        }

        // Then
        XCTAssertFalse(libraryManager.isTemporaryLibrary(savedLibrary.url), "Saved library should not be temporary")
    }

    // MARK: - Open/Close Tests

    func testOpenExistingLibrary() async throws {
        // Given - Create and save a library
        let library = libraryManager.createNewLibrary()
        let saveURL = tempDirectory.appendingPathComponent("Existing.fichero")
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // Close it
        libraryManager.closeLibrary(library.id)
        XCTAssertNil(libraryManager.getLibrary(id: library.id), "Library should be closed")

        // When - Reopen it
        let reopened = libraryManager.openLibrary(at: saveURL)

        // Then
        XCTAssertEqual(reopened.displayName, "Existing", "Should have correct display name")
        XCTAssertEqual(reopened.url, saveURL, "Should have correct URL")
        XCTAssertEqual(libraryManager.openLibraries.count, 1, "Should have one open library")
    }

    func testOpenSameLibraryTwiceReturnsSameInstance() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        let saveURL = tempDirectory.appendingPathComponent("Test.fichero")
        try libraryManager.saveLibrary(library.id, to: saveURL)

        // When
        let opened1 = libraryManager.openLibrary(at: saveURL)
        let opened2 = libraryManager.openLibrary(at: saveURL)

        // Then
        XCTAssertEqual(opened1.id, opened2.id, "Should return same library instance")
        XCTAssertEqual(libraryManager.openLibraries.count, 1, "Should not create duplicate")
    }

    func testGetLibrary() async throws {
        // Given
        let library = libraryManager.createNewLibrary()

        // When
        let retrieved = libraryManager.getLibrary(id: library.id)

        // Then
        XCTAssertNotNil(retrieved, "Should find library by ID")
        XCTAssertEqual(retrieved?.id, library.id, "Should return correct library")
    }

    func testCloseLibrary() async throws {
        // Given
        let library = libraryManager.createNewLibrary()
        XCTAssertEqual(libraryManager.openLibraries.count, 1)

        // When
        libraryManager.closeLibrary(library.id)

        // Then
        XCTAssertEqual(libraryManager.openLibraries.count, 0, "Library should be removed")
        XCTAssertNil(libraryManager.getLibrary(id: library.id), "Library should not be findable")
    }
}
