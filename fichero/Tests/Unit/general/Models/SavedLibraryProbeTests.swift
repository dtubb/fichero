@testable import Fichero
import XCTest

/// A saved library whose volume does not answer costs launch the probe's timeout, not the volume's (#7105).
@MainActor
final class SavedLibraryProbeTests: XCTestCase {
    private let libraryManager = LibraryManager.shared
    private var tempDirectory: URL!
    private var originalPaths: [String]?

    override func setUpWithError() throws {
        try super.setUpWithError()
        originalPaths = EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey)
        libraryManager.openLibraries = []
        libraryManager.unansweredSavedLibraryPaths = []
        libraryManager.backendIsReady = false
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("SavedLibraryProbeTests")
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        libraryManager.openLibraries = []
        libraryManager.unansweredSavedLibraryPaths = []
        if let originalPaths {
            EngineConfig.defaults.set(originalPaths, forKey: LibraryManager.openLibraryPathsKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: LibraryManager.openLibraryPathsKey)
        }
        try? FileManager.default.removeItem(at: tempDirectory)
        try super.tearDownWithError()
    }

    private func makeLibrary(_ name: String) throws -> URL {
        let url = tempDirectory.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    func testTheProbeGivesUpOnAPathThatDoesNotAnswerAndHandsItsLateAnswerOn() {
        let gate = DispatchSemaphore(value: 0)
        let late = expectation(description: "the late answer is handed on")
        let started = Date()

        let answers = SavedLibraryProbe.answers(
            for: ["/here", "/gone", "/hangs"],
            timeout: 0.2,
            exists: { path in
                if path == "/hangs" { gate.wait() }
                return path != "/gone"
            },
            late: { path, exists in
                if path == "/hangs", exists { late.fulfill() }
            }
        )

        XCTAssertLessThan(Date().timeIntervalSince(started), 2.0, "the probe waited for the path that hangs")
        XCTAssertEqual(answers, ["/here": .present, "/gone": .missing, "/hangs": .unanswered])
        gate.signal()
        wait(for: [late], timeout: 5)
    }

    func testRestoreGoesOnWithoutALibraryThatDoesNotAnswerAndOpensItWhenItDoes() async throws {
        let quick = try makeLibrary("Quick.fichero")
        let slow = try makeLibrary("Slow.fichero")
        EngineConfig.defaults.set([quick.path, slow.path], forKey: LibraryManager.openLibraryPathsKey)
        let gate = DispatchSemaphore(value: 0)
        let slowPath = slow.path
        let started = Date()

        libraryManager.restoreSavedLibraries(probeTimeout: 0.2) { path in
            if path == slowPath { gate.wait() }
            return true
        }

        XCTAssertLessThan(Date().timeIntervalSince(started), 2.0, "restore held the main thread for the slow volume")
        XCTAssertEqual(libraryManager.openLibraries.map(\.url), [quick], "only the library that answered is open")
        XCTAssertEqual(
            EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey), [quick.path, slow.path],
            "a library that has not answered must stay in the saved list"
        )
        let current = libraryManager.currentLibraryId

        gate.signal()
        for _ in 0..<200 where libraryManager.openLibraries.count < 2 {
            try await Task.sleep(nanoseconds: 25_000_000)
        }

        XCTAssertEqual(Set(libraryManager.openLibraries.map(\.url)), [quick, slow], "the late answer opens the library")
        XCTAssertEqual(libraryManager.currentLibraryId, current, "a late library must not take the window")
        XCTAssertEqual(libraryManager.unansweredSavedLibraryPaths, [])
    }

    func testALateAnswerOfMissingDropsThePathFromTheSavedList() throws {
        let quick = try makeLibrary("Quick.fichero")
        let gonePath = tempDirectory.appendingPathComponent("Gone.fichero").path
        EngineConfig.defaults.set([quick.path, gonePath], forKey: LibraryManager.openLibraryPathsKey)
        libraryManager.unansweredSavedLibraryPaths = [gonePath]
        _ = libraryManager.openLibrary(at: quick)
        XCTAssertEqual(
            EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey), [quick.path, gonePath])

        libraryManager.savedLibraryAnsweredLate(path: gonePath, exists: false)

        XCTAssertEqual(EngineConfig.defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey), [quick.path])
        XCTAssertEqual(libraryManager.openLibraries.map(\.url), [quick])
    }
}
