@testable import Fichero
import FicheroAPIClient
import OpenAPIRuntime
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

    @Test("a refusal with the engine's detail says the engine's words")
    func engineWords() async {
        let body = UndocumentedPayload(body: HTTPBody(#"{"detail":"This batch is already finished."}"#))
        let error = await BatchServiceError.refused(409, body)

        #expect(error.errorDescription == "This batch is already finished.")
        #expect(await BatchServiceError.refused(503, UndocumentedPayload()).errorDescription == "Unexpected response: HTTP 503")
    }
}
