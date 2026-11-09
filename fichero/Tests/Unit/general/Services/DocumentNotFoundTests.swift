@testable import Fichero
import Testing

/// A missing document says so (#6477, #6479). What breaks without these: a restored selection of a deleted library
/// reads "Unexpected response from server" and the store keeps its error state instead of falling back to the root set.
struct DocumentNotFoundTests {
    @Test("a not-found is told apart from an unexpected response and worded as missing")
    func notFound() {
        #expect(DocumentServiceError.notFound("d1").isNotFound)
        #expect(!DocumentServiceError.unexpectedResponse.isNotFound)
        #expect(!DocumentServiceError.httpStatus(operation: "save", code: 409).isNotFound)
        #expect(DocumentServiceError.notFound("d1").errorDescription == "Document not found: d1")
    }

    @Test("an artifact 404 says it is missing; another status keeps its code")
    func artifact404() {
        #expect(ArtifactServiceError.unexpectedResponse(404).errorDescription == "Not found: it is no longer in this library")
        #expect(ArtifactServiceError.unexpectedResponse(500).errorDescription?.contains("500") == true)
    }
}
