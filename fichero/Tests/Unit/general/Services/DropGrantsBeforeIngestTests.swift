@testable import Fichero
import XCTest

#if os(macOS)

/// A Finder drop is the person's grant (#5219). Daniel dropped a folder from ~/Fichero Test Corpus on Dev
/// Local and got "Unexpected response from import service (status: 403)": the engine refuses a path
/// outside its allowed roots whatever the sandbox, and the app sent no grant because it was unsandboxed.
/// What breaks without these: the grant is skipped again (a bare 403 on every drop outside the roots), the
/// ingest races ahead of the grant, or the refusal loses its reason and its Grant Access….
@MainActor
final class DropGrantsBeforeIngestTests: XCTestCase {
    /// Records what the engine was handed, and when.
    private final class RecordingEngine: EngineAccessGranting {
        var events: [String] = []
        var refuses = false
        func grantAccess(toPath path: String, bookmark: Data) async throws {
            events.append("grant \(URL(fileURLWithPath: path).lastPathComponent)")
            if refuses { throw ImportServiceError.serverError("refused") }
        }
    }

    private var saved: (any EngineAccessGranting)?
    private var folder: URL!

    override func setUp() async throws {
        saved = FolderAccessManager.shared.engineAccessService
        folder = FileManager.default.temporaryDirectory.appendingPathComponent("Fichero Test Corpus \(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        FolderAccessManager.shared.engineAccessService = saved
        try? FileManager.default.removeItem(at: folder)
    }

    func testADropGrantsTheEngineAndThenIngests() async throws {
        let engine = RecordingEngine()
        FolderAccessManager.shared.engineAccessService = engine
        try await FolderAccessManager.grantThenEngineWork(
            grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(self.folder) },
            engineWork: { engine.events.append("ingest") }
        )
        XCTAssertEqual(engine.events, ["grant \(folder.lastPathComponent)", "ingest"],
                       "the grant reaches the engine, sandboxed or not, and before the ingest reads the folder")
    }

    func testUnsandboxedARefusedGrantLetsTheEnginesOwnAnswerStand() async throws {
        try XCTSkipIf(SandboxEnvironment.isSandboxed, "the unsandboxed rule; sandboxed, a refused grant is fatal")
        let engine = RecordingEngine()
        engine.refuses = true
        FolderAccessManager.shared.engineAccessService = engine
        try await FolderAccessManager.shared.saveBookmarkIfDirectory(folder)
        XCTAssertEqual(engine.events.count, 1, "asked once; the ingest goes on and the engine answers for the path")
    }

    func testTheRefusalIsReadByItsCodeOrItsOldWords() throws {
        let path = "/Users/me/Fichero Test Corpus"
        let coded = Data(#"{"detail":{"code":"library_outside_allowed_locations","path":"/Users/me/Corpus"}}"#.utf8)
        XCTAssertEqual(ImportServiceError.refusal(fromBody: coded, path: path)?.errorDescription?.contains("Corpus"), true)
        let worded = Data(#"{"detail":"Ingest path is not in an allowed location: /Users/me/Fichero Test Corpus"}"#.utf8)
        guard case .outsideAllowedLocations(let refused, _)? = ImportServiceError.refusal(fromBody: worded, path: path) else {
            return XCTFail("the engine's current 403 text must still be read as the refusal")
        }
        XCTAssertEqual(refused, path)
        XCTAssertNil(ImportServiceError.refusal(fromBody: Data(#"{"detail":"Owner access required"}"#.utf8), path: path),
                     "any other 403 is not a place to grant")
        XCTAssertTrue(ImportServiceError.outsideAllowedLocations(path: path).errorDescription?.contains("Add a Folder") == true,
                      "the message names its remedy")
    }

    /// #5484: the engine now allows any folder its owner picks in Fichero's own panel (setup's Add a
    /// Folder…, File › Import…), and its refusal says so. The app used to say "Choose Grant Access…,
    /// then drop it again", a two-step remedy the engine no longer needs. WHY this test: the person must
    /// read the ENGINE's sentence, as it sends it in the flat `{detail, code, path}` 403, and never the
    /// old "drop it again"; if the app re-worded it, the two would drift again.
    func testTheRefusalSaysTheEnginesSentenceNeverDropItAgain() throws {
        let sentence = "Ingest path is not in an allowed location: /Users/me/Corpus. To allow it, choose its "
            + "folder with Add a Folder\u{2026} or File \u{203A} Import\u{2026} in Fichero."
        let object: [String: Any] = ["detail": sentence, "code": "library_outside_allowed_locations", "path": "/Users/me/Corpus"]
        let flat = try JSONSerialization.data(withJSONObject: object)
        let refusal = try XCTUnwrap(ImportServiceError.refusal(fromBody: flat, path: "/elsewhere"))
        XCTAssertEqual(refusal.errorDescription, sentence, "the engine's words, as it sent them")
        guard case .outsideAllowedLocations(let refused, _) = refusal else { return XCTFail("read as the refusal") }
        XCTAssertEqual(refused, "/Users/me/Corpus", "the engine's path wins over the one the app asked about")
        let fallback = ImportServiceError.outsideAllowedLocations(path: "/Users/me/Corpus").errorDescription ?? ""
        XCTAssertFalse(fallback.contains("drop it again"), "no second step: picking the folder is the permission")
        XCTAssertTrue(fallback.contains("File \u{203A} Import\u{2026}"), "without the engine's words, the same remedy")
    }
}
#endif
