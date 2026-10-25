@testable import Fichero
import XCTest

/// Cancelling Set Up of a NEW project deletes the project it made, and nothing else (#6117,
/// `source.onboard.cancel-deletes-the-new-project`, docs/contributor_manual/specs/source/models-chains-and-projects.md).
@MainActor
final class NewProjectDiscardTests: XCTestCase {
    private var folder: URL!
    private var trashed: [URL] = []

    override func setUp() async throws {
        try await super.setUp()
        folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("FicheroTests").appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        trashed = []
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: folder)
        try await super.tearDown()
    }

    private func store() -> NewProjectStore {
        let store = NewProjectStore(
            libraryManager: LibraryManager.shared, openInEngine: { _ in },
            trash: { [unowned self] url in
                trashed.append(url)
                try FileManager.default.removeItem(at: url)
            })
        store.place = .chosen(folder)
        return store
    }

    func testCancelDeletesTheProjectTheWindowMade() async throws {
        let store = store()
        let created = await store.create()
        let made = try XCTUnwrap(created)
        XCTAssertTrue(FileManager.default.fileExists(atPath: made.url.path))
        XCTAssertTrue(store.discard())
        XCTAssertEqual(trashed, [made.url])
        XCTAssertFalse(FileManager.default.fileExists(atPath: made.url.path))
        XCTAssertNil(LibraryManager.shared.getLibrary(id: made.id), "gone from the sidebar's open set")
        XCTAssertNil(store.created)
    }

    func testAStoreThatMadeNothingDeletesNothing() throws {
        let existing = folder.appendingPathComponent("Existing.fichero")
        try FileManager.default.createDirectory(at: existing, withIntermediateDirectories: true)
        XCTAssertFalse(store().discard())
        XCTAssertTrue(trashed.isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: existing.path))
    }

    func testATrashFailureIsKeptForTheWindowToSayAndTheProjectIsStillClosed() async throws {
        struct Refused: Error {}
        let store = NewProjectStore(libraryManager: LibraryManager.shared, openInEngine: { _ in }, trash: { _ in throw Refused() })
        store.place = .chosen(folder)
        let created = await store.create()
        let made = try XCTUnwrap(created)
        XCTAssertFalse(store.discard())
        XCTAssertNotNil(store.errorMessage, "the window shows it before it closes")
        XCTAssertNil(LibraryManager.shared.getLibrary(id: made.id))
    }

    func testDeleteProjectAndASetUpCancelGoThroughOneCloseThenTrashSequence() async throws {
        // The sequence itself: closed first, then the package to the Trash, whatever the caller.
        var steps: [String] = []
        let url = folder.appendingPathComponent("P.fichero")
        try LibraryManager.closeAndTrash(url, close: { steps.append("close") }, trash: { steps.append("trash \($0.lastPathComponent)") })
        XCTAssertEqual(steps, ["close", "trash P.fichero"])

        // A cancelled new project goes through it: its close unregisters the library, then its Trash is asked.
        let store = store()
        let created = await store.create()
        let made = try XCTUnwrap(created)
        XCTAssertTrue(store.discard())
        XCTAssertEqual(trashed, [made.url], "the store's Trash is the one closeAndTrash calls")
        XCTAssertNil(LibraryManager.shared.getLibrary(id: made.id), "closed before the Trash was asked")
    }

    func testTheTrashRefusingAfterTheCloseIsThrownNotSwallowed() {
        struct Refused: Error {}
        var closed = false
        XCTAssertThrowsError(try LibraryManager.closeAndTrash(folder, close: { closed = true }, trash: { _ in throw Refused() }))
        XCTAssertTrue(closed)
    }

    func testOnlyANewProjectsSetUpCancelDeletes() {
        XCTAssertTrue(FirstRunWindow.cancelDeletesTheProject(in: .newProject))
        XCTAssertFalse(FirstRunWindow.cancelDeletesTheProject(in: .setUp), "Set Up on an existing project never deletes")
        XCTAssertFalse(FirstRunWindow.cancelDeletesTheProject(in: .firstRun))
    }
}
