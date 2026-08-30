@testable import Fichero
import Foundation
import Testing

@Suite("DocumentSource")
struct DocumentSourceTests {

    @Test("source identity and relevance survive a Codable round trip")
    func codingRoundTrip() throws {
        let source = DocumentSource(
            id: "source-1",
            documentId: "document-1",
            documentName: "Letter.pdf",
            excerpt: "A relevant passage.",
            relevanceScore: 0.92
        )

        let decoded = try JSONDecoder().decode(DocumentSource.self, from: JSONEncoder().encode(source))

        #expect(decoded == source)
        #expect(decoded.id == "source-1")
        #expect(decoded.documentId == "document-1")
        #expect(decoded.relevanceScore == 0.92)
    }
}
