@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class AddMaterialURLProtocol: URLProtocol {
    struct Seen { let method: String; let path: String; let library: String?; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []
    nonisolated(unsafe) static var folderPath = ""

    override static func canInit(with request: URLRequest) -> Bool {
        (request.url?.path ?? "").hasPrefix("/api/ingest")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        let path = request.url?.path ?? ""
        Self.seen.append(Seen(method: request.httpMethod ?? "GET", path: path,
                              library: request.value(forHTTPHeaderField: "X-Fichero-Library-Path"), body: body))
        let json: String = switch (request.httpMethod ?? "GET", path) {
        case ("POST", "/api/ingest/folder"):
            #"{"task_id":"t1","status":"pending","path":"\#(Self.folderPath)"}"#
        case ("POST", "/api/ingest/file"):
            #"{"id":"d9","name":"letter.jpg","doc_type":"file","expected_thumbnail_path":"t","expected_display_path":"d"}"#
        default:
            #"{"task_id":"t1","status":"completed","path":"\#(Self.folderPath)","progress":1,"#
                + #""total":2,"processed":2,"document_ids":["d1","d2"]}"#
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class GrantingEngine: EngineAccessGranting {
    func grantAccess(toPath path: String, bookmark: Data) async throws {}
}

/// Set Up's Add material reaches THE NEW PROJECT (2026-10-11, the run that broke): after Add a Folder… no
/// `POST /api/ingest/folder` reached the new project, its Sources stayed empty and Start ran on nothing, and a folder
/// was recorded as one file ("Is a directory"). Driven through the real store and the project's own ImportService.
@MainActor
@Suite(.serialized)
struct SetUpAddsMaterialToTheProjectTests {
    private static let newProject = "/tmp/Colombia-\(UUID().uuidString).fichero"

    private func importer() -> ImportService {
        AddMaterialURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AddMaterialURLProtocol.self]
        return ImportService(ficheroClient: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                          libraryPath: Self.newProject,
                                                          session: URLSession(configuration: configuration)))
    }

    /// A folder and a file in a temporary place, the engine's grant accepted; `body` runs, then they are removed.
    private func withMaterial(_ body: (URL, URL) async throws -> Void) async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("setup-\(UUID().uuidString)")
        let folder = root.appendingPathComponent("CACIQUES_INDIOS,17,D.5")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let file = root.appendingPathComponent("letter.jpg")
        try Data([0xFF, 0xD8]).write(to: file)
        let saved = FolderAccessManager.shared.engineAccessService
        FolderAccessManager.shared.engineAccessService = GrantingEngine()
        defer {
            FolderAccessManager.shared.engineAccessService = saved
            try? FileManager.default.removeItem(at: root)
        }
        AddMaterialURLProtocol.folderPath = folder.path
        try await body(folder, file)
    }

    private func store(_ way: SetupWayIn) -> RecipeSetupStore {
        let store = RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                           libraryPath: Self.newProject))
        store.wayIn = way
        return store
    }

    @Test("a folder added with Copy goes into the new project through POST /api/ingest/folder")
    func folderReachesTheProject() async throws {
        try await withMaterial { folder, _ in
            // The folder as a picker can hand it back: no trailing slash, so its path alone does not say "folder".
            let picked = URL(fileURLWithPath: folder.path, isDirectory: false)
            let store = store(.copy)
            await store.addMaterial([picked], importer: importer())
            let ingest = try #require(AddMaterialURLProtocol.seen.first { $0.path == "/api/ingest/folder" })
            #expect(ingest.body["path"] as? String == folder.path)
            #expect(ingest.body["recursive"] as? Bool == true)
            #expect(ingest.body["copy_mode"] as? Bool == true, "Copy, as chosen")
            #expect(ingest.library?.contains("Colombia-") == true, "into the new project, never the always-there one")
            #expect(store.materialAdded != nil)
            #expect(!store.isAddingMaterial, "Start no longer waits")
        }
    }

    @Test("a folder and a file together: the folder through the folder import, the file as a file, never the folder")
    func folderAndFileEachTheirWay() async throws {
        try await withMaterial { folder, file in
            let store = store(.link)
            await store.addMaterial([URL(fileURLWithPath: folder.path, isDirectory: false), file], importer: importer())
            // The closures are hoisted out of #expect: the macro and a typed-throws closure trip the compiler.
            let seen = AddMaterialURLProtocol.seen
            let sawFolderImport = seen.contains(where: { (request: AddMaterialURLProtocol.Seen) in request.path == "/api/ingest/folder" })
            let filePaths: [String?] = seen.filter({ (request: AddMaterialURLProtocol.Seen) in request.path == "/api/ingest/file" })
                .map({ (request: AddMaterialURLProtocol.Seen) in request.body["path"] as? String })
            let allToTheProject = seen.allSatisfy({ (request: AddMaterialURLProtocol.Seen) in request.library?.contains("Colombia-") == true })
            #expect(sawFolderImport)
            #expect(filePaths == [file.path], "the file as a file")
            #expect(!filePaths.contains(folder.path), "a folder is never one file")
            #expect(allToTheProject)
        }
    }

    @Test("a folder handed back without a trailing slash is still a folder")
    func folderWithoutTrailingSlash() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("plain-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        #expect(ImportService.isDirectory(URL(fileURLWithPath: folder.path, isDirectory: false)))
        #expect(!ImportService.isDirectory(folder.appendingPathComponent("absent.jpg")))
    }

    @Test("Start waits while material is being added, and says why")
    func startWaitsForTheMaterial() {
        let store = RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                           libraryPath: Self.newProject))
        store.isAddingMaterial = true
        #expect(!store.canStart)
        #expect(store.startDisabledReason == "Fichero is still adding your material; Start waits for it.")
    }
}
