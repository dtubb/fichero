@testable import Fichero
import Testing

@Suite("BatchServiceError")
struct BatchServiceErrorTests {

    @Test("validation errors preserve the backend diagnosis")
    func validationErrorDescription() {
        let error = BatchServiceError.validationError("max_concurrent must be at most 50")

        #expect(error.errorDescription == "Validation error: max_concurrent must be at most 50")
    }

    @Test("unexpected responses preserve the HTTP status")
    func unexpectedResponseDescription() {
        let error = BatchServiceError.unexpectedResponse(503)

        #expect(error.errorDescription == "Unexpected response: HTTP 503")
    }
}
