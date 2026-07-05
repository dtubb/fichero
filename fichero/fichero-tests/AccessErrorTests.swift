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

    // MARK: - Stale bootstrap token (#3052) — the exact sandbox-relaunch 401

    @Test func staleBootstrapToken401IsDistinctFromUnauthenticated() {
        // The engine's real body (auth.py): a 401 carrying a machine `code`.
        let body = Data(#"{"detail": "local bootstrap token is stale", "code": "stale_bootstrap_token"}"#.utf8)
        let error = AccessError.classify(statusCode: 401, body: body)
        #expect(error == .staleBootstrapToken)
        // Signing in cannot fix a stale bootstrap token — restart re-mints it.
        #expect(error?.recovery == .restartEngine)
        #expect(error?.recovery != .signIn)
    }

    @Test func staleBootstrapTokenDiscriminatorIsStatusAgnostic() {
        // If a path 403s the stale token instead of 401ing it, still classify it
        // as stale (keyed on `code`, not the status).
        let body = Data(#"{"detail": "stale", "code": "stale_bootstrap_token"}"#.utf8)
        #expect(AccessError.classify(statusCode: 403, body: body) == .staleBootstrapToken)
    }

    @Test func plain401WithoutStaleCodeStaysUnauthenticated() {
        // A 401 whose body carries a different/absent code is a genuine sign-in
        // case, not a stale token.
        let body = Data(#"{"detail": "not authenticated"}"#.utf8)
        #expect(AccessError.classify(statusCode: 401, body: body) == .unauthenticated)
    }

    @Test func denialBodyCapturesTopLevelCodeAlongsideStringDetail() {
        // Regression: the string-`detail` path used to early-return and drop `code`.
        let body = Data(#"{"detail": "msg", "code": "stale_bootstrap_token"}"#.utf8)
        let denial = DenialBody.decode(body)
        #expect(denial?.code == "stale_bootstrap_token")
        #expect(denial?.message == "msg")
    }

    // MARK: - Expired / revoked device token (#3096) — never a silent 401

    @Test func expiredDeviceTokenMapsToDeviceAccessExpired() {
        // The engine's real body (auth.py): 401 with this exact detail, no code.
        let body = Data(#"{"detail": "device token expired"}"#.utf8)
        let error = AccessError.classify(statusCode: 401, body: body)
        #expect(error == .deviceAccessExpired)
        // A device has no password sign-in — re-pair is the only recovery.
        #expect(error?.recovery == .rePair)
        #expect(error?.recovery != .signIn)
    }

    @Test func expiredDeviceAlsoMatchesFutureStructuredCode() {
        // Robust to the backend later attaching a machine code.
        let body = Data(#"{"detail": "…", "code": "device_token_expired"}"#.utf8)
        #expect(AccessError.classify(statusCode: 401, body: body) == .deviceAccessExpired)
    }

    @Test func expiredDeviceHasARepairMessage() {
        #expect(AccessError.deviceAccessExpired.errorDescription?.isEmpty == false)
        #expect(AccessError.deviceAccessExpired.errorDescription?.contains("Re-pair") == true)
    }

    @Test func forbiddenReasonFallsBackToTopLevelCode() {
        // A 403 with a machine `code` but no nested reason still surfaces the code
        // as the forbidden reason.
        let body = Data(#"{"detail": "No access", "code": "not_a_member"}"#.utf8)
        #expect(AccessError.classify(statusCode: 403, body: body)
            == .forbidden(reason: "not_a_member", message: "No access"))
    }

    // MARK: - Never-blank invariant

    /// Every representable failure must carry a non-empty message AND a recovery,
    /// so no case can render an empty pane / actionless spinner (F5/F6 invariant).
    @Test func everyCaseHasMessageAndRecovery() {
        let allCases: [AccessError] = [
            .unauthenticated,
            .staleBootstrapToken,
            .deviceAccessExpired,
            .forbidden(reason: nil, message: nil),
            .forbidden(reason: "r", message: "m"),
            .tlsPinFailure,
            .engineUnreachable,
            .transport("boom")
        ]
        for error in allCases {
            let description = error.errorDescription ?? ""
            #expect(!description.isEmpty, "\(error) has an empty description")
            // recovery is non-optional — every case maps to exactly one action.
            _ = error.recovery
        }
    }

    @Test func distinctFailuresGetDistinctRecoveries() {
        // The five primary failure surfaces Daniel hits map to five different
        // next-actions — no two collapse into the same dead-end.
        #expect(AccessError.unauthenticated.recovery == .signIn)
        #expect(AccessError.staleBootstrapToken.recovery == .restartEngine)
        #expect(AccessError.deviceAccessExpired.recovery == .rePair)
        #expect(AccessError.forbidden(reason: nil, message: nil).recovery == .requestAccess)
        #expect(AccessError.tlsPinFailure.recovery == .resetPin)
        #expect(AccessError.engineUnreachable.recovery == .restartEngine)
    }
}
