//
//  EffectiveAttributesOriginTests.swift
//  FicheroTests
//
//  The Inspector says where each value came from (`proto.app.inspector-says-where-from`, #5365): the
//  words are pure logic on what the engine's `effective-attributes` returns, and the decode goes through
//  the generated client against a stub scoped to this suite's own host.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class OriginMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var attributes = ""

    private static let prototypes = """
    {"count":1,"items":[{"id":"p1","dimension":"document_prototype","key":"eap_digital_folder",
    "label":"EAP digital folder","attributes":{},"is_builtin":true}]}
    """

    private static func document(id: String, name: String) -> String {
        """
        {"id":"\(id)","name":"\(name)","expected_thumbnail_path":"t","expected_display_path":"d","attributes":{}}
        """
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "origin.test" }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        let path = url.path
        let body: String
        if path.hasSuffix("/effective-attributes") {
            body = Self.attributes
        } else if path.contains("/api/classifications") {
            body = Self.prototypes
        } else if path.hasSuffix("/box12") {
            body = Self.document(id: "box12", name: "Caja 12")
        } else {
            body = Self.document(id: "f1", name: "Folder")
        }
        guard let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class EffectiveAttributesOriginTests: XCTestCase {
    private let names = ["box12": "Caja 12"]
    private let labels = ["eap_digital_folder": "EAP digital folder"]

    private func words(_ origin: AttributeOrigin) -> String? {
        OriginWords.words(origin, ancestorNames: names, prototypeLabels: labels)
    }

    /// WHY: the four origins read exactly as the spec words them, and an empty value has nothing to explain.
    func testEachOriginReadsInWords() {
        XCTAssertEqual(words(.init(kind: .here)), "set here")
        XCTAssertEqual(words(.init(kind: .inherited, from: "box12")), "from Caja 12")
        XCTAssertEqual(words(.init(kind: .default, from: "eap_digital_folder")), "default of EAP digital folder")
        XCTAssertNil(words(.init(kind: .empty)))
    }

    /// WHY: a machine's value names its model; a person's name shows only when the source carries one.
    func testASourceNamesWhoSetTheValue() {
        let machine = AttributeOrigin.Source(byMachine: true, model: "qwen3-vl", name: nil)
        XCTAssertEqual(words(.init(kind: .here, source: machine)), "Fichero (qwen3-vl)")
        let person = AttributeOrigin.Source(byMachine: false, model: nil, name: "Ana")
        XCTAssertEqual(words(.init(kind: .here, source: person)), "Ana")
        let unnamed = AttributeOrigin.Source(byMachine: false, model: nil, name: nil)
        XCTAssertEqual(words(.init(kind: .here, source: unnamed)), "set here")
    }

    /// WHY: an ancestor we could not name must not leak its raw id into a sentence.
    func testAnUnreadableAncestorIsNotShownAsAnId() {
        XCTAssertEqual(words(.init(kind: .inherited, from: "zz9")), "from an ancestor")
    }

    /// WHY: only a value set here is plain; inherited and default values are greyed.
    func testOnlyAValueSetHereIsPlain() {
        XCTAssertFalse(OriginWords.isGreyed(.init(kind: .here)))
        XCTAssertFalse(OriginWords.isGreyed(nil))
        XCTAssertTrue(OriginWords.isGreyed(.init(kind: .inherited, from: "box12")))
        XCTAssertTrue(OriginWords.isGreyed(.init(kind: .default, from: "eap_digital_folder")))
    }

    /// WHY: the kind row says whether the kind is the node's own or came from above.
    func testTheKindRowSaysWhereTheKindCameFrom() {
        XCTAssertEqual(OriginWords.kindWords(rule: "own", from: nil, ancestorNames: names), "set here")
        XCTAssertEqual(OriginWords.kindWords(rule: "inherited", from: "box12", ancestorNames: names), "from Caja 12’s kind")
        XCTAssertNil(OriginWords.kindWords(rule: "none", from: nil, ancestorNames: names))
    }

    private func makeService() -> EntityService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OriginMockURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://origin.test")!, libraryPath: "/tmp/origin.fichero",
                                   session: URLSession(configuration: configuration))
        return EntityService(ficheroClient: client)
    }

    /// WHY: what the engine sends per key must reach the Inspector intact, with the ancestor named.
    func testTheEnginesOriginsDecodeAndNameTheAncestor() async throws {
        OriginMockURLProtocol.attributes = """
        {"prototype_key":null,"effective_prototype_key":"eap_digital_folder","kind_rule":"inherited","kind_from":"box12",
         "declarations":{"reference":{"type":"text","inherits":true},"title":{"type":"text"}},
         "values":{"reference":"AB-1","title":"Mine"},
         "origins":{"reference":{"origin":"inherited","from":"box12","source":null},
                    "title":{"origin":"here","from":null,"source":{"by":"machine","model":"qwen3-vl"}}}}
        """
        let found = try await makeService().effectiveAttributes(documentId: "f1")
        XCTAssertEqual(found.effectivePrototypeKey, "eap_digital_folder")
        XCTAssertEqual(found.kindRule, "inherited")
        XCTAssertEqual(found.kindFrom, "box12")
        XCTAssertEqual(found.origins["reference"], .init(kind: .inherited, from: "box12"))
        XCTAssertEqual(found.origins["title"]?.source, .init(byMachine: true, model: "qwen3-vl", name: nil))
        XCTAssertEqual(found.ancestorNames["box12"], "Caja 12")
    }
}
