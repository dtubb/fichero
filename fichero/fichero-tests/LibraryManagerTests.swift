@testable import Fichero
import XCTest

@MainActor
final class LibraryManagerTests: XCTestCase {
    var libraryManager: LibraryManager!
    var tempDirectory: URL!

    override func setUp() async throws {
        try await super.setUp()

        // Use the shared instance (singleton pattern)
        libraryManager = LibraryManager.shared
        libraryManager.openLibraries = []
        libraryManager.currentLibraryId = nil
        libraryManager.untitledCounter = 1
        libraryManager.backendIsReady = false
        libraryManager.loadedLibraryIds = []
        libraryManager.loadingLibraryIds = []
        libraryManager.libraryIdsAwaitingGrant = []
        libraryManager.librariesLoadVersion = 0

        // Create a temporary test directory
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroTests")
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
        libraryManager.libraryIdsAwaitingGrant = []
        libraryManager.librariesLoadVersion = 0

        // Clean up temporary test directory
        if FileManager.default.fileExists(atPath: tempDirectory.path) {
            try? FileManager.default.removeItem(at: tempDirectory)
        }

        try await super.tearDown()
    }

    private func restoreEngineHost(_ value: String?) {
        if let value {
            UserDefaults.standard.set(value, forKey: EngineConfig.userDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: EngineConfig.userDefaultsKey)
        }
    }

    // MARK: - Registry Reconciliation (#3393)

    func testReconciliationOpensRegistryLibrariesMissingLocally() {
        let global = LibraryManager.globalLibraryId
        let plan = LibraryManager.registryReconciliation(
            openLibraries: [(id: global, path: "/L/Global.fichero")],
            registryPaths: ["/L/Global.fichero", "/L/A.fichero", "/L/B.fichero"],
            globalLibraryId: global
        )
        XCTAssertEqual(plan.pathsToOpen, ["/L/A.fichero", "/L/B.fichero"],
                       "registry libraries not open locally are opened")
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    func testReconciliationDropsOpenLibrariesTheBackendClosed() {
        let global = LibraryManager.globalLibraryId
        let stale = UUID()
        let plan = LibraryManager.registryReconciliation(
            openLibraries: [(id: global, path: "/L/Global.fichero"),
                            (id: stale, path: "/L/Closed.fichero")],
            registryPaths: ["/L/Global.fichero"],
            globalLibraryId: global
        )
        XCTAssertEqual(plan.idsToDrop, [stale], "a library absent from the registry is dropped")
        XCTAssertTrue(plan.pathsToOpen.isEmpty)
    }

    func testReconciliationNeverDropsTheGlobalLibrary() {
        let global = LibraryManager.globalLibraryId
        let plan = LibraryManager.registryReconciliation(
            openLibraries: [(id: global, path: "/L/Global.fichero")],
            registryPaths: [],  // backend lists nothing
            globalLibraryId: global
        )
        XCTAssertTrue(plan.idsToDrop.isEmpty, "Global is never dropped, even when absent from the registry")
    }

    func testReconciliationIsNoOpWhenInSync() {
        let global = LibraryManager.globalLibraryId
        let libA = UUID()
        let plan = LibraryManager.registryReconciliation(
            openLibraries: [(id: global, path: "/L/Global.fichero"), (id: libA, path: "/L/A.fichero")],
            registryPaths: ["/L/Global.fichero", "/L/A.fichero"],
            globalLibraryId: global
        )
        XCTAssertTrue(plan.pathsToOpen.isEmpty)
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    func testReconciliationComparesPathsNFCNormalized() {
        // Same library, one side NFD (decomposed "é"), the other NFC — must match,
        // so a Unicode-normalization mismatch never double-opens or false-drops.
        let global = LibraryManager.globalLibraryId
        let libA = UUID()
        let nfd = "/L/Cafe\u{0301}.fichero"   // e + combining acute
        let nfc = "/L/Caf\u{00E9}.fichero"    // é precomposed
        let plan = LibraryManager.registryReconciliation(
            openLibraries: [(id: libA, path: nfd)],
            registryPaths: [nfc],
            globalLibraryId: global
        )
        XCTAssertTrue(plan.pathsToOpen.isEmpty, "NFD-open vs NFC-registry is the same library")
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    // MARK: - Reconcile snapshot guard (#3988)

    func testShouldReconcileOnlyWhenFetchSucceededAndNonEmpty() {
        XCTAssertTrue(
            LibraryManager.shouldReconcile(fetchError: nil, registryPaths: ["/L/A.fichero"]),
            "a clean, non-empty snapshot reconciles"
        )
    }

    func testShouldNotReconcileAfterFailedFetch() {
        // A failed fetch leaves `libraries` STALE — reconciling could false-drop an
        // open library, so a non-nil fetchError must block reconcile even when the
        // (stale) snapshot is non-empty.
        XCTAssertFalse(
            LibraryManager.shouldReconcile(
                fetchError: "offline",
                registryPaths: ["/L/A.fichero"]
            ),
            "a failed fetch must never reconcile against its stale snapshot"
        )
    }

    func testShouldNotReconcileOnEmptySnapshot() {
        // Empty is ambiguous (genuinely-empty backend vs cold-store failure); never
        // clear the sidebar on it. (Successful-empty → reconcile-to-empty deferred.)
        XCTAssertFalse(
            LibraryManager.shouldReconcile(fetchError: nil, registryPaths: []),
            "an empty snapshot is treated as 'do not touch'"
        )
    }

    // MARK: - Load-success gating (#3986-B)

    func testLibraryLoadSucceededOnlyWhenConnectedAndNoError() {
        XCTAssertTrue(
            LibraryManager.libraryLoadSucceeded(error: nil, isConnected: true),
            "a connected load with no error counts as loaded"
        )
    }

    func testLibraryLoadNotSucceededWhenDisconnected() {
        XCTAssertFalse(
            LibraryManager.libraryLoadSucceeded(error: nil, isConnected: false),
            "a load that never connected must not be marked loaded"
        )
    }

    func testLibraryLoadNotSucceededWhenErrorSwallowed() {
        // DocumentStore swallows a load failure into `error` (never throws), so a
        // non-nil error must count as failure even if `isConnected` is stale-true.
        struct LoadFailure: Error {}
        XCTAssertFalse(
            LibraryManager.libraryLoadSucceeded(error: LoadFailure(), isConnected: true),
            "a swallowed load error must not be marked loaded"
        )
    }

    // MARK: - Grant-before-load gating (#3986-A)

    func testLoadDefersWhileLibraryAwaitsSandboxGrant() async {
        // A library whose sandbox grant is still in flight must not load — the
        // guard short-circuits before any package read, so the restore /
        // backend-ready path can't beat the grant's network round-trip (#3773).
        let library = libraryManager.createNewLibrary()
        libraryManager.backendIsReady = true
        libraryManager.libraryIdsAwaitingGrant.insert(library.id)

        await libraryManager.loadLibraryDataIfNeeded(for: library)

        XCTAssertFalse(
            libraryManager.loadedLibraryIds.contains(library.id),
            "a grant-pending library must not be marked loaded"
        )
        XCTAssertFalse(
            libraryManager.loadingLibraryIds.contains(library.id),
            "a grant-pending library must not even start loading"
        )
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

    func testLibraryLoadDefersUntilBackendReady() async throws {
        // When
        let library = libraryManager.createNewLibrary()

        // Then
        XCTAssertFalse(libraryManager.backendIsReady, "Backend should not be marked ready during plain library creation")
        XCTAssertFalse(
            libraryManager.loadedLibraryIds.contains(library.id),
            "Library data should not be marked loaded before backend readiness"
        )
        XCTAssertFalse(
            libraryManager.loadingLibraryIds.contains(library.id),
            "Library data load should not start before backend readiness"
        )
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

    func testCreateNewLibraryUsesConfiguredEngineHost() async throws {
        // Given
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }
        let remoteHost = URL(string: "https://host.tailnet.example")!
        UserDefaults.standard.set(remoteHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

        // When
        let library = libraryManager.createNewLibrary()

        // Then
        XCTAssertEqual(library.ficheroClient.baseURL, remoteHost)
        XCTAssertEqual(library.apiClient.baseURL, remoteHost.appendingPathComponent("api"))
    }

    func testReconfigureGeneratedClientsForCurrentHostUpdatesOpenLibrary() async throws {
        // Given
        let originalHost = UserDefaults.standard.string(forKey: EngineConfig.userDefaultsKey)
        defer { restoreEngineHost(originalHost) }
        let firstHost = URL(string: "https://first.tailnet.example")!
        let secondHost = URL(string: "https://second.tailnet.example")!
        UserDefaults.standard.set(firstHost.absoluteString, forKey: EngineConfig.userDefaultsKey)

        let library = libraryManager.createNewLibrary()
        XCTAssertEqual(library.ficheroClient.baseURL, firstHost)

        // When
        UserDefaults.standard.set(secondHost.absoluteString, forKey: EngineConfig.userDefaultsKey)
        libraryManager.reconfigureGeneratedClientsForCurrentHost()

        // Then
        XCTAssertEqual(library.ficheroClient.baseURL, secondHost)
        XCTAssertEqual(library.apiClient.baseURL, secondHost.appendingPathComponent("api"))
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

    // MARK: - #2472 Sidebar launch population

    /// librariesLoadVersion must start at 0 so SidebarView's
    /// .onChange(of: librariesLoadVersion) fires on the FIRST load completion.
    func testLibrariesLoadVersionStartsAtZero() {
        XCTAssertEqual(libraryManager.librariesLoadVersion, 0)
    }

    /// loadLibraryDataIfNeeded is re-entrant-guarded: an already-loaded library
    /// must not bump librariesLoadVersion a second time (prevents double-rebuild).
    func testLibrariesLoadVersionNotIncrementedForAlreadyLoadedLibrary() async {
        let library = libraryManager.createNewLibrary()
        libraryManager.loadedLibraryIds.insert(library.id)

        await libraryManager.loadLibraryDataIfNeeded(for: library)

        XCTAssertEqual(
            libraryManager.librariesLoadVersion, 0,
            "Already-loaded library must not increment librariesLoadVersion"
        )
    }

    /// After adoptPairedRemoteLibrary resets loadedLibraryIds, librariesLoadVersion
    /// is still 0 — confirming the sidebar's onChange will fire when loading completes.
    func testAdoptPairedRemoteLibraryDoesNotIncrementLoadVersion() {
        // adoptPairedRemoteLibrary only runs on iOS (requiresExternalBackendConnection),
        // so we simulate its effect: clear loadedLibraryIds without bumping the version.
        libraryManager.loadedLibraryIds = []

        XCTAssertEqual(
            libraryManager.librariesLoadVersion, 0,
            "librariesLoadVersion must be 0 before data loads so sidebar onChange fires on completion"
        )
    }
}
