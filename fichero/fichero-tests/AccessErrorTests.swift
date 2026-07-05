@testable import Fichero
import Foundation
import Testing

/// F5 taxonomy: every failure classifies to a distinct case with a next action,
/// so no call site is left with a bare 403 / spinner (never-silent-fail).
struct AccessErrorTests {
    @Test func status401IsUnauthenticatedSignIn() {
        let error = AccessError.classify(statusCode: 401, body: nil)
        #expect(error == .unauthenticated)
        #expect(error?.recovery == .signIn)
    }

    @Test func status403DecodesStructuredDenialBody() {
        let body = Data(#"{"detail": {"reason": "not_a_member", "message": "Ask the owner for access."}}"#.utf8)
        let error = AccessError.classify(statusCode: 403, body: body)
        #expect(error == .forbidden(reason: "not_a_member", message: "Ask the owner for access."))
        #expect(error?.recovery == .requestAccess)
        #expect(error?.errorDescription == "Ask the owner for access.")
    }

    @Test func status403WithStringDetailStillReadsAsForbidden() {
        let body = Data(#"{"detail": "Forbidden"}"#.utf8)
        let error = AccessError.classify(statusCode: 403, body: body)
        #expect(error == .forbidden(reason: nil, message: "Forbidden"))
    }

    @Test func status403WithNoBodyFallsBackToGenericMessage() {
        let error = AccessError.classify(statusCode: 403, body: nil)
        #expect(error == .forbidden(reason: nil, message: nil))
        #expect(error?.errorDescription == "You don't have access to this.")
    }

    @Test func nonAccessStatusesAreNil() {
        #expect(AccessError.classify(statusCode: 200, body: nil) == nil)
        #expect(AccessError.classify(statusCode: 404, body: nil) == nil)
        #expect(AccessError.classify(statusCode: 500, body: nil) == nil)
    }

    @Test func tlsPinFailureDetectedInUnderlyingErrorChain() {
        // The -9807 pin rejection is nested under NSUnderlyingErrorKey, not on the
        // top-level URLError — the classifier must walk the chain.
        let ssl = NSError(domain: NSOSStatusErrorDomain, code: -9807, userInfo: nil)
        let wrapper = NSError(
            domain: NSURLErrorDomain,
            code: URLError.secureConnectionFailed.rawValue,
            userInfo: [NSUnderlyingErrorKey: ssl]
        )
        #expect(AccessError.classify(wrapper) == .tlsPinFailure)
        #expect(AccessError.classify(wrapper).recovery == .resetPin)
    }

    @Test func unreachableTransportErrors() {
        #expect(AccessError.classify(URLError(.cannotConnectToHost)) == .engineUnreachable)
        #expect(AccessError.classify(URLError(.timedOut)) == .engineUnreachable)
        #expect(AccessError.classify(URLError(.timedOut)).recovery == .restartEngine)
    }

    @Test func otherErrorsCarryTheirDescription() {
        let error = AccessError.classify(URLError(.badURL))
        if case .transport = error {
            // ok — carried through, not swallowed
        } else {
            Issue.record("expected .transport, got \(error)")
        }
        #expect(error.recovery == .retry)
    }
}
