@testable import Fichero
import XCTest

@MainActor
final class LibraryWorkspaceRootTests: XCTestCase {
    private var libraryManager: LibraryManager!
    private var tempDirectory: URL!

    override func setUp() async throws {
        try await super.setUp()

        libraryManager = LibraryManager.shared
        libraryManager.openLibraries = []
        libraryManager.currentLibraryId = nil
        libraryManager.untitledCounter = 1
        libraryManager.backendIsReady = false
        libraryManager.loadedLibraryIds = []
        libraryManager.loadingLibraryIds = []

        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("LibraryWorkspaceRootTests")
            .appendingPathComponent(UUID().uuidString)

        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        libraryManager.openLibraries = []
        libraryManager.currentLibraryId = nil
        libraryManager.untitledCounter = 1
        libraryManager.backendIsReady = false
        libraryManager.loadedLibraryIds = []
        libraryManager.loadingLibraryIds = []

        if FileManager.default.fileExists(atPath: tempDirectory.path) {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        try await super.tearDown()
    }

    func testActiveLibraryPrefersCurrentLibrary() throws {
        let first = libraryManager.createNewLibrary()
        let second = libraryManager.createNewLibrary()
        libraryManager.currentLibraryId = second.id

        let resolved = LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: libraryManager.currentLibraryId,
            windowLibraryId: first.id,
            libraryManager: libraryManager
        )

        XCTAssertEqual(resolved?.id, second.id)
    }

    func testActiveLibraryFallsBackToWindowLibrary() throws {
        let first = libraryManager.createNewLibrary()
        _ = libraryManager.createNewLibrary()
        libraryManager.currentLibraryId = UUID()

        let resolved = LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: libraryManager.currentLibraryId,
            windowLibraryId: first.id,
            libraryManager: libraryManager
        )

        XCTAssertEqual(resolved?.id, first.id)
    }

    func testActiveLibraryFallsBackToGlobalLibrary() throws {
        let resolved = LibraryWorkspaceSelection.activeLibrary(
            currentLibraryId: nil,
            windowLibraryId: UUID(),
            libraryManager: libraryManager
        )

        XCTAssertNil(resolved)
    }

    func testDocumentURLIsNilForTemporaryLibrary() throws {
        let library = libraryManager.createNewLibrary()

        let resolvedURL = LibraryWorkspaceSelection.documentURL(
            for: library.url,
            libraryManager: libraryManager
        )

        XCTAssertNil(resolvedURL)
    }

    func testDocumentURLIsPreservedForSavedLibrary() throws {
        let library = libraryManager.createNewLibrary()
        let savedURL = tempDirectory.appendingPathComponent("Saved.fichero")
        try libraryManager.saveLibrary(library.id, to: savedURL)

        let resolvedURL = LibraryWorkspaceSelection.documentURL(
            for: savedURL,
            libraryManager: libraryManager
        )

        XCTAssertEqual(resolvedURL, savedURL)
    }

    func testWorkspaceRootStoresExplicitWindowState() throws {
        let library = libraryManager.createNewLibrary()
        let windowState = WindowState(libraryId: library.id)
        let root = LibraryWorkspaceRoot(
            library: library,
            windowState: windowState,
            executionObserver: WorkflowExecutionObserver()
        )

        XCTAssertTrue(root.windowState === windowState)
    }
}
