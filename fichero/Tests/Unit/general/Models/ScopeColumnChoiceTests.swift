//
//  ScopeColumnChoiceTests.swift
//  FicheroTests
//
//  A scope's template and its saved column choice (`proto.template.per-scope-column-choice`, #6282):
//  the app reads the engine's columns, sends a person's narrowing through the engine's routes and files
//  the audit row each answer names as one ⌘Z step. Driven through the generated client against a stub
//  scoped to this suite's own host.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class ColumnsMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    nonisolated(unsafe) private static var log: [(path: String, method: String)] = []

    static func reset(_ handler: @escaping (URLRequest) -> (Int, String)) {
        lock.lock()
        self.handler = handler
        log = []
        lock.unlock()
    }

    static func requests(to path: String) -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return log.filter { $0.path == path }.map(\.method)
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "columns.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        Self.lock.lock()
        Self.log.append((url.path, request.httpMethod ?? ""))
        let handler = Self.handler
        Self.lock.unlock()
        let (status, json) = handler?(request) ?? (404, "{}")
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class ScopeColumnChoiceTests: XCTestCase {
    @MainActor
    private final class Engine: UndoSetEngine {
        let projectPath: String? = "/tmp/columns.fichero"
        var sets: [[String]] = []
        func undoSet(auditIds: [String]) async throws -> [String] {
            sets.append(auditIds)
            return ["u1"]
        }
    }

    private static let mixedJSON = """
    {"columns":[{"key":"title","kind":"tbase"},{"key":"sender","kind":"tletter"}],"mixed":true,
     "prototypes":["tbase","tletter"]}
    """

    private let narrowed = """
    {"columns":[{"key":"sender","kind":"tletter"}],"mixed":false,"prototypes":["tletter"],
     "choice":{"hide":["title"]},"audit_id":"a-1"}
    """

    private func makeService() -> EntityService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ColumnsMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://columns.test")!,
            libraryPath: "/tmp/columns.fichero",
            session: URLSession(configuration: configuration)
        )
        return EntityService(ficheroClient: client)
    }

    override func tearDown() {
        ColumnsMockURLProtocol.handler = nil
        super.tearDown()
    }

    /// WHY: the columns are the engine's; the app asks the scope node and shows what it is told.
    func testTheTemplateIsReadFromTheScopesRoute() async throws {
        ColumnsMockURLProtocol.reset { _ in
            (200, Self.mixedJSON)
        }
        let template = try await makeService().scopeTemplate(documentId: "scope")
        XCTAssertEqual(template.columns.map(\.key), ["title", "sender"])
        XCTAssertTrue(template.mixed)
        XCTAssertNil(template.choice)
        XCTAssertEqual(ColumnsMockURLProtocol.requests(to: "/api/documents/scope/template"), ["GET"])
    }

    /// WHY: narrowing is a PUT on the scope and clearing a DELETE; each answer names the audit row, and
    /// registering it makes one ⌘Z step that the engine takes back as a set. No window, no step.
    func testAChoiceAndItsClearingEachFileOneUndoStep() async throws {
        ColumnsMockURLProtocol.reset { _ in (200, self.narrowed) }
        let service = makeService()
        let steps = WindowSteps()
        let engine = Engine()

        let answer = try await service.setColumnChoice(documentId: "scope", hide: ["title"])
        XCTAssertEqual(answer.auditId, "a-1")
        XCTAssertEqual(answer.choice?.hide, ["title"])
        XCTAssertNotNil(answer.registerUndo(service: engine, steps: steps))
        XCTAssertEqual(steps.undoName, "Change Columns")
        XCTAssertNil(answer.registerUndo(service: engine, steps: nil))

        _ = try await service.clearColumnChoice(documentId: "scope")
        XCTAssertEqual(ColumnsMockURLProtocol.requests(to: "/api/documents/scope/column-choice"), ["PUT", "DELETE"])
    }

    /// WHY: an unknown scope is refused in words, not swallowed.
    func testARefusalIsThrown() async {
        ColumnsMockURLProtocol.reset { _ in (404, #"{"detail":"Document not found"}"#) }
        do {
            _ = try await makeService().scopeTemplate(documentId: "nope")
            XCTFail("an unknown scope is refused")
        } catch {
            XCTAssertNotNil(error as? EntityService.ServiceError)
        }
    }
}
