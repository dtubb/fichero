@testable import Fichero
import Foundation
import Testing

struct ChatDocumentDropPayloadTests {
    private let uppercaseID = "8B2F4D6A-1C3E-4F5B-9A7D-0E2C6F8B4A9D"
    private let lowercaseID = "8b2f4d6a-1c3e-4f5b-9a7d-0e2c6f8b4a9d"

    @Test("bare document UUID is accepted")
    func bareDocumentIDAccepted() {
        #expect(ChatDocumentDropPayload.documentID(from: uppercaseID) == uppercaseID)
    }

    @Test("legacy doc-prefixed document UUID is accepted")
    func legacyDocPrefixedIDAccepted() {
        #expect(ChatDocumentDropPayload.documentID(from: "doc:\(uppercaseID)") == uppercaseID)
    }

    @Test("normalization trims surrounding whitespace")
    func trimsWhitespace() {
        #expect(ChatDocumentDropPayload.documentID(from: "\n  doc:\(lowercaseID)  \t") == lowercaseID)
    }

    @Test("valid lowercase UUID casing is preserved")
    func preservesLowercaseID() {
        #expect(ChatDocumentDropPayload.documentID(from: lowercaseID) == lowercaseID)
    }

    @Test("arbitrary text is rejected")
    func rejectsArbitraryText() {
        #expect(ChatDocumentDropPayload.documentID(from: "drop this document please") == nil)
    }

    @Test("non-document prefixed payload is rejected")
    func rejectsNonDocumentPrefix() {
        #expect(ChatDocumentDropPayload.documentID(from: "chat:\(uppercaseID)") == nil)
    }

    @Test("malformed doc-prefixed payload is rejected")
    func rejectsMalformedDocPrefix() {
        #expect(ChatDocumentDropPayload.documentID(from: "doc:not-a-document-id") == nil)
    }

    @Test("UTF-8 data payload decodes to document UUID")
    func decodesDataPayload() {
        let data = Data("doc:\(uppercaseID)".utf8)
        #expect(ChatDocumentDropPayload.documentID(from: data as NSData) == uppercaseID)
    }
}
