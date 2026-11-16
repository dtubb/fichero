@testable import Fichero
import Foundation
import Testing

/// A long image operation asked for as a job says in words why it did not finish (`image.ops.long-operation-is-a-job`, #6384).
struct ImageJobErrorTests {
    @Test("a failed job says the engine's reason, a stopped one says it was stopped")
    func wordsForTheOutcome() {
        #expect(ImageJobError.failed("Not enough memory for this scan.").errorDescription == "Not enough memory for this scan.")
        #expect(ImageJobError.stopped.errorDescription == "The operation was stopped.")
        #expect(ImageJobError.refused(503).errorDescription == "The engine did not take the operation (HTTP 503).")
    }
}
