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
        // The five primary failure surfaces the user hits map to five different
        // next-actions — no two collapse into the same dead-end.
        #expect(AccessError.unauthenticated.recovery == .signIn)
        #expect(AccessError.staleBootstrapToken.recovery == .restartEngine)
        #expect(AccessError.deviceAccessExpired.recovery == .rePair)
        #expect(AccessError.forbidden(reason: nil, message: nil).recovery == .requestAccess)
        #expect(AccessError.tlsPinFailure.recovery == .resetPin)
        #expect(AccessError.engineUnreachable.recovery == .restartEngine)
    }

    @Test func connectionDiagnosesExplainTheCorrectRecovery() {
        #expect(AppState.diagnosis(for: .staleBootstrapToken).contains("saved engine token is out of date"))
        #expect(
            AppState.diagnosis(for: .unauthenticated)
                == "Fichero connected to the engine, but the saved sign-in is out of date. Reset Sign-In & Retry."
        )
        #expect(AppState.diagnosis(for: .tlsPinFailure).contains("Reset the certificate"))
    }

    // MARK: - Connection-failure title never over-claims "not running" (#3341)

    @Test func unreachableEmbeddedSaysCantConnectNotNotRunning() {
        // The engine may be running but we couldn't reach it (wrong port /
        // transient) — the actionable screen must NOT claim it's "not running".
        let title = ConnectionPresentation.failureTitle(
            accessError: .engineUnreachable,
            authBroken: false,
            ownership: .externalLocal
        )
        #expect(title == "Can't Connect to Server")
        #expect(title != "Server Not Running")
    }

    @Test func unclassifiedEmbeddedFailureStillNeverSaysNotRunning() {
        let title = ConnectionPresentation.failureTitle(
            accessError: nil,
            authBroken: false,
            ownership: .externalLocal
        )
        #expect(title == "Can't Connect to Server")
    }

    @Test func authBrokenRoutesToTheActionableAuthTitle() {
        // Health-200-but-auth-broken on a user-managed engine: connected to the
        // engine, stale sign-in → the "Can't Authenticate" screen, never "not running".
        let title = ConnectionPresentation.failureTitle(
            accessError: .unauthenticated,
            authBroken: true,
            ownership: .externalLocal
        )
        #expect(title == "Can't Authenticate to Server")
    }

    @Test func embeddedAuthBrokenUsesAppOwnedCopy() {
        let title = ConnectionPresentation.failureTitle(
            accessError: .unauthenticated,
            authBroken: true,
            ownership: .appManaged
        )
        #expect(title == "Fichero Couldn't Authenticate to Its Server")
        #expect(!title.contains("Sign-In"))
    }

    @Test func externalUnreachableReadsAsBackendNotReachable() {
        let title = ConnectionPresentation.failureTitle(
            accessError: .engineUnreachable,
            authBroken: false,
            ownership: .remote
        )
        #expect(title == "Backend Not Reachable")
    }

    // MARK: - Grant Access… (#5198)

    /// The engine's 403 for a package outside every location it may open, as the app receives it: the
    /// flat body with its code. ONLY that code offers Grant Access -- a membership denial (another
    /// person's library, `library_access_denied`) still says to ask the owner.
    @Test func aLibraryOutsideTheAllowedLocationsOffersGrantAccessAndAMembershipDenialDoesNot() {
        let outside = Data(#"{"detail": "'/Volumes/X/Acceptance 2026-09-27b.fichero' is a .fichero package, but it is outside every location this engine may open (allowed roots and security-scoped grants). Open it from the app so access can be granted, or move it into an allowed location such as Documents.", "code": "library_outside_allowed_locations"}"#.utf8)
        let error = AccessError.classify(statusCode: 403, body: outside)
        #expect(error?.recovery == .grantAccess)
        #expect(LibraryAccessDeniedView.resolvePrimaryAction(
            for: error ?? .unauthenticated, isAuthenticated: true, isOwnerAccess: true
        ) == .grantAccess, "the owner of a library outside the allowed places gets Grant Access, not Try Again")

        let membership = Data(#"{"detail": "not a member", "code": "library_access_denied", "required": "read"}"#.utf8)
        let denied = AccessError.classify(statusCode: 403, body: membership)
        #expect(denied?.recovery == .requestAccess)
        #expect(LibraryAccessDeniedView.resolvePrimaryAction(
            for: denied ?? .unauthenticated, isAuthenticated: true, isOwnerAccess: false
        ) == .requestAccess, "another person's library: ask its owner, never a folder picker")
    }

    /// Grant Access… with the panel stubbed: the panel opens AT the library (selected, named in the
    /// message); a choice is granted to the engine and THEN the load is retried; a cancel does neither.
    @MainActor
    @Test func grantAccessGrantsTheChoiceThenRetriesAndACancelDoesNothing() async throws {
        let library = URL(fileURLWithPath: "/Volumes/Archive/Acceptance 2026-09-27b.fichero")
        final class Log { var steps: [String] = []; var asked: LibraryAccessGrant.Request? }
        let log = Log()
        let chosen = library.deletingLastPathComponent()
        let grant = LibraryAccessGrant(
            choose: { request in log.asked = request; return chosen },
            grant: { url in log.steps.append("grant " + url.lastPathComponent) },
            retry: { log.steps.append("retry") }
        )
        #expect(try await grant.run(for: library))
        #expect(log.steps == ["grant Archive", "retry"], "the grant lands before the load is tried again")
        #expect(log.asked?.directoryURL == library, "the panel opens at the library itself")
        #expect(log.asked?.message.hasPrefix("Fichero may not open \u{201C}Acceptance 2026-09-27b\u{201D}") == true)

        log.steps = []
        let cancelled = LibraryAccessGrant(choose: { _ in nil }, grant: { _ in log.steps.append("grant") },
                                           retry: { log.steps.append("retry") })
        #expect(try await cancelled.run(for: library) == false)
        #expect(log.steps.isEmpty, "a cancel grants nothing and retries nothing")
    }
}
