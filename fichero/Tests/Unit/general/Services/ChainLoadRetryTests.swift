@testable import Fichero
import Testing

@Suite("ChainLoadRetry")
struct ChainLoadRetryTests {
    @Test("models.chains.load-retries-a-cancelled-request: a cancelled request is asked again, three times, waiting longer each time")
    func cancelledRequestIsRetried() {
        let waits = (1...3).map { ChainLoadRetry.wait(afterAttempt: $0, requestCancelled: true, taskCancelled: false) }
        #expect(waits == [0.5, 1.0, 1.5])
        #expect(ChainLoadRetry.wait(afterAttempt: 4, requestCancelled: true, taskCancelled: false) == nil, "then it stops")
    }

    @Test("models.chains.load-retries-a-cancelled-request: a cancelled task and any other error stop at once")
    func otherStopsAreNotRetried() {
        #expect(ChainLoadRetry.wait(afterAttempt: 1, requestCancelled: true, taskCancelled: true) == nil)
        #expect(ChainLoadRetry.wait(afterAttempt: 1, requestCancelled: false, taskCancelled: false) == nil)
    }
}
