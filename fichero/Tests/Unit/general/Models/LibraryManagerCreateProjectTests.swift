@testable import Fichero
import XCTest

/// A project created in the app, and the setup it offers, through the REAL create path
/// (`LibraryManager.createProject(at:)` — what File › New Library… runs once the save panel
/// has a location, in a window and with no window alike).
///
/// Specs: `create.project.appears-and-is-selected` (docs/contributor_manual/specs/ui/sidebar-crud.md),
/// `source.onboard.new-project-offers-setup` and `source.onboard.reachable`
/// (docs/contributor_manual/specs/source/models-chains-and-projects.md). Issues #5430, #5421.
///
/// XCTest on the `LibraryManager.shared` singleton, like its neighbour `LibraryManagerTests`:
/// the sidebar reads that singleton's `openLibraries`, so a fresh instance would test a list
/// no window ever shows. `setUp`/`tearDown` reset the singleton the same way the neighbour does.
@MainActor
final class LibraryManagerCreateProjectTests: XCTestCase {
    private var libraryManager: LibraryManager!
    private var tempDirectory: URL!
    private var originalFirstRunCompleted = false
    private var originalOpenPaths: [String]?
    private var originalNames: [String: Any]?

    override func setUp() async throws {
        try await super.setUp()
        libraryManager = LibraryManager.shared
        resetSingleton()
        originalFirstRunCompleted = FeatureManager.shared.firstRunCompleted
        originalOpenPaths = EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey)
        originalNames = EngineConfig.defaults.dictionary(forKey: LibraryManager.libraryDisplayNamesByPathKey)
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroTests")
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        resetSingleton()
        FeatureManager.shared.firstRunCompleted = originalFirstRunCompleted
        if let originalOpenPaths {
            EngineConfig.defaults.set(originalOpenPaths, forKey: LibraryManager.openLibraryPathsKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: LibraryManager.openLibraryPathsKey)
        }
        if let originalNames {
            EngineConfig.defaults.set(originalNames, forKey: LibraryManager.libraryDisplayNamesByPathKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: LibraryManager.libraryDisplayNamesByPathKey)
        }
        try? FileManager.default.removeItem(at: tempDirectory)
        try await super.tearDown()
    }

    private func resetSingleton() {
        libraryManager.openLibraries = []
        libraryManager.currentLibraryId = nil
        libraryManager.untitledCounter = 1
        libraryManager.backendIsReady = false
        libraryManager.loadedLibraryIds = []
        libraryManager.loadingLibraryIds = []
        libraryManager.libraryIdsAwaitingGrant = []
        libraryManager.librariesLoadVersion = 0
        libraryManager.createdProjectId = nil
        libraryManager.setUpRequestedLibraryId = nil
    }

    /// The Global library sits first in every real sidebar; install it the way
    /// `loadGlobalLibrary` does, without the network.
    private func installGlobalLibrary() -> LibraryManager.LibraryReference {
        let library = LibraryManager.LibraryReference(
            url: tempDirectory.appendingPathComponent("global.fichero"),
            document: FicheroDocument(),
            displayName: "Local",
            id: LibraryManager.globalLibraryId,
            startAccessing: false
        )
        libraryManager.openLibraries.insert(library, at: 0)
        return library
    }

    // MARK: - create.project.appears-and-is-selected

    /// WHY: the maintainer created a new library and it was not in the sidebar (#5430). The
    /// sidebar's rows are `openLibraries`; this pins that the create path adds exactly ONE entry,
    /// in place (every other library is the same object at the same position — nothing rebuilt
    /// or reloaded), at the saved location, and marks it as the project to select. If this goes
    /// red, a created project is missing, duplicated, or left unselected in the sidebar.
    func test_create_project_appears_and_is_selected() throws {
        let global = installGlobalLibrary()
        let otherURL = tempDirectory.appendingPathComponent("Other.fichero")
        try FileManager.default.createDirectory(at: otherURL, withIntermediateDirectories: true)
        let other = libraryManager.openLibrary(at: otherURL, makeCurrent: false)
        let before = libraryManager.openLibraries

        let finalURL = tempDirectory.appendingPathComponent("Marshall Diaries.fichero")
        let created = try libraryManager.createProject(at: finalURL)

        XCTAssertEqual(libraryManager.openLibraries.count, before.count + 1, "one row added, no more")
        XCTAssertTrue(libraryManager.openLibraries[0] === global, "Global stays first and is not rebuilt")
        XCTAssertTrue(libraryManager.openLibraries[1] === created, "the new project lands after Global")
        XCTAssertTrue(libraryManager.openLibraries[2] === other, "the other project is untouched, in place")
        XCTAssertEqual(created.url, finalURL, "the row is the SAVED project, not the temporary one")
        XCTAssertEqual(created.displayName, "Marshall Diaries")
        XCTAssertEqual(libraryManager.currentLibraryId, created.id, "the window switches to it")
        XCTAssertEqual(libraryManager.createdProjectId, created.id, "the sidebar is told to select its row")
    }

    /// WHY: the root cause of #5430. `saveLibrary` moved the temporary package to the chosen
    /// location but never re-persisted the open-library list, and that list skips temporary
    /// packages — so the new project was never in it. The next launch restored the list without
    /// it and the project vanished from the sidebar. If this goes red, created projects stop
    /// surviving a relaunch again.
    func test_create_project_appears_after_relaunch() throws {
        _ = installGlobalLibrary()
        let finalURL = tempDirectory.appendingPathComponent("Istmina.fichero")

        let created = try libraryManager.createProject(at: finalURL)

        let saved = EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey) ?? []
        XCTAssertTrue(
            saved.contains(created.url.path.nfcNormalized),
            "the saved project must be in the list the next launch restores; saved: \(saved)"
        )
        XCTAssertFalse(
            saved.contains { $0.contains("Untitled-") },
            "the temporary path it was created at must not be what is remembered"
        )
    }

    // MARK: - source.onboard.new-project-offers-setup

    /// WHY: setup was gated on `!featureManager.firstRunCompleted`, so after the app's first
    /// launch a new project never offered setup (#5430). `firstRunCompleted` governs only the
    /// app's first launch. If this goes red, a new project after first run opens with no setup.
    func test_source_onboard_new_project_offers_setup() throws {
        _ = installGlobalLibrary()
        FeatureManager.shared.firstRunCompleted = true

        let created = try libraryManager.createProject(at: tempDirectory.appendingPathComponent("Chocó.fichero"))

        XCTAssertEqual(libraryManager.setUpRequestedLibraryId, created.id)
        XCTAssertTrue(
            projectSetUpIsDue(
                requestedLibraryId: libraryManager.setUpRequestedLibraryId,
                windowLibraryId: created.id,
                firstRunShowing: false
            ),
            "the window showing the new project presents setup for it, first run completed or not"
        )
        XCTAssertFalse(
            projectSetUpIsDue(
                requestedLibraryId: libraryManager.setUpRequestedLibraryId,
                windowLibraryId: LibraryManager.globalLibraryId,
                firstRunShowing: false
            ),
            "a window on another project does not present it"
        )
    }

    /// WHY: when the app's own first run is showing, that flow already runs the recipe steps;
    /// stacking a second setup sheet on it would ask the same questions twice.
    func test_source_onboard_new_project_offers_setup_waits_for_first_run() throws {
        let created = try libraryManager.createProject(at: tempDirectory.appendingPathComponent("A.fichero"))

        XCTAssertFalse(
            projectSetUpIsDue(
                requestedLibraryId: libraryManager.setUpRequestedLibraryId,
                windowLibraryId: created.id,
                firstRunShowing: true
            )
        )
    }

    // MARK: - source.onboard.reachable

    /// WHY: setup could only be found in Inspector › Info › Recipe (#5421). File › Set Up
    /// Project… and the empty project's Set Up… both ask for setup of the window's project
    /// through `requestSetUp(for:)`, the one request the window presents. If this goes red,
    /// either entry point stops opening setup, or opens it for the wrong project.
    func test_source_onboard_reachable() throws {
        let otherURL = tempDirectory.appendingPathComponent("Selected.fichero")
        try FileManager.default.createDirectory(at: otherURL, withIntermediateDirectories: true)
        let selected = libraryManager.openLibrary(at: otherURL, makeCurrent: true)
        XCTAssertNil(libraryManager.setUpRequestedLibraryId, "opening a project asks nothing")

        libraryManager.requestSetUp(for: selected.id)

        XCTAssertTrue(
            projectSetUpIsDue(
                requestedLibraryId: libraryManager.setUpRequestedLibraryId,
                windowLibraryId: selected.id,
                firstRunShowing: false
            )
        )
    }

    /// WHY: the empty project's main view offers Set Up… only when the PROJECT is empty and
    /// loaded — not for an empty folder inside a full project, not for a filter that hid every
    /// row, and not before the load has said what is there.
    func test_source_onboard_reachable_empty_project_offers_set_up() {
        XCTAssertTrue(projectOffersSetUp(reason: .noCollectionSelected, isLoaded: true, rootCollections: []))
        XCTAssertFalse(
            projectOffersSetUp(
                reason: .noCollectionSelected, isLoaded: true,
                rootCollections: [Document(docType: .file, name: "1893 diary.pdf")]
            ),
            "a project with material is not empty"
        )
        XCTAssertFalse(
            projectOffersSetUp(reason: .noCollectionSelected, isLoaded: false, rootCollections: []),
            "an unloaded project says nothing about its contents"
        )
        XCTAssertFalse(
            projectOffersSetUp(reason: .filteredOut(query: "x"), isLoaded: true, rootCollections: []),
            "a filtered-out body is hidden, not empty"
        )
    }
}
