//
//  PrototypeEditCopiesBuiltinTests.swift
//  FicheroTests
//
//  A column change on a built-in prototype (`proto.template.edit-copies-a-builtin`, #6282): the engine
//  lands it on a project-owned child, and the editor says so and shows the copy. Driven through the
//  generated client against a stub scoped to this suite's own host.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class CopyMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var answer = ""
    nonisolated(unsafe) static var methods: [String] = []

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "copy.test" }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        Self.methods.append("\(request.httpMethod ?? "") \(url.path)")
        guard let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.answer.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class PrototypeEditCopiesBuiltinTests: XCTestCase {
    private func makeService() -> EntityService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CopyMockURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://copy.test")!, libraryPath: "/tmp/copy.fichero",
                                   session: URLSession(configuration: configuration))
        return EntityService(ficheroClient: client)
    }

    override func setUp() {
        super.setUp()
        CopyMockURLProtocol.methods = []
    }

    /// WHY: the save of a built-in answers with the child the engine made; the editor must follow THAT key,
    /// not the one it sent, or it would keep showing the built-in the change never touched.
    func testASaveReturnsTheValueTheEngineLandedItOn() async throws {
        CopyMockURLProtocol.answer = """
        {"id":"c1","dimension":"document_prototype","key":"letter-copy","label":"Letter (this project)",
         "parent_key":"letter","attributes":{},"is_builtin":false}
        """
        let saved = try await makeService().updateDocumentPrototype(
            valueId: "b1", label: "Letter", parentKey: nil, color: nil, attributes: []
        )
        XCTAssertEqual(saved.key, "letter-copy")
        XCTAssertEqual(saved.parentKey, "letter")
        XCTAssertEqual(CopyMockURLProtocol.methods, ["PATCH /api/classifications/b1"])
    }

    /// WHY: a person who edited "Letter" and finds "Letter (this project)" selected must be told why.
    func testTheEditorSaysWhenTheChangeWentToACopy() {
        let said = EntityService.copiedNotice(edited: "letter", saved: "letter-copy", label: "Letter")
        XCTAssertEqual(said, "“Letter” is built in, so your change is saved as a copy for this project (letter-copy).")
        XCTAssertNil(EntityService.copiedNotice(edited: "mine", saved: "mine", label: "Mine"))
    }
}
