@testable import Fichero
import Foundation
import Testing

/// F6: LibraryAccessDeniedView must render a distinct, actionable state for EACH
/// failure — never a blank pane or a dead-end. These exercise the pure decision
/// (`resolvePrimaryAction`) that drives the primary button, for every failure
/// case crossed with the relevant identity postures.
@MainActor
struct LibraryAccessDeniedViewTests {
    private typealias Action = LibraryAccessDeniedView.PrimaryAction

    private func action(
        _ error: AccessError,
        isAuthenticated: Bool? = nil,
        isOwnerAccess: Bool = false
    ) -> Action {
        LibraryAccessDeniedView.resolvePrimaryAction(
            for: error,
            isAuthenticated: isAuthenticated,
            isOwnerAccess: isOwnerAccess
        )
    }

    // MARK: - Identity-independent failures each get their own action

    @Test func tlsPinFailureOffersResetPin() {
        #expect(action(.tlsPinFailure) == .resetPin)
    }

    @Test func engineUnreachableOffersRestart() {
        #expect(action(.engineUnreachable) == .restartEngine)
    }

    @Test func staleBootstrapTokenOffersRestartNotSignIn() {
        // The #3052 trap: a stale bootstrap token must NOT send the user to a
        // sign-in that can't fix it.
        #expect(action(.staleBootstrapToken) == .restartEngine)
        #expect(action(.staleBootstrapToken) != .signIn)
    }

    @Test func expiredDeviceOffersRePairNotSignIn() {
        // #3096: an expired/revoked device token has no password sign-in recovery.
        #expect(action(.deviceAccessExpired) == .rePair)
        #expect(action(.deviceAccessExpired) != .signIn)
    }

    @Test func unauthenticatedOffersSignIn() {
        #expect(action(.unauthenticated) == .signIn)
    }

    @Test func transportOffersRetry() {
        #expect(action(.transport("boom")) == .retry)
    }

    // MARK: - Forbidden is disambiguated by identity

    @Test func forbiddenWithoutIdentityRequestsAccess() {
        // Identity not loaded (nil) → can't assume; ask for access (safe default).
        #expect(action(.forbidden(reason: nil, message: nil), isAuthenticated: nil) == .requestAccess)
    }

    @Test func forbiddenWhenNotSignedInOffersSignIn() {
        #expect(action(.forbidden(reason: nil, message: nil), isAuthenticated: false) == .signIn)
    }

    @Test func forbiddenAsOwnerOffersRestart() {
        // You own the library but it's refusing you → engine-state problem, restart.
        #expect(action(
            .forbidden(reason: nil, message: nil),
            isAuthenticated: true,
            isOwnerAccess: true
        ) == .restartEngine)
    }

    @Test func forbiddenAsSignedInNonOwnerRequestsAccess() {
        #expect(action(
            .forbidden(reason: nil, message: nil),
            isAuthenticated: true,
            isOwnerAccess: false
        ) == .requestAccess)
    }

    // MARK: - Never a dead-end: every case yields an action + the view builds

    @Test func everyFailureCaseResolvesToAnActionAndBuildsAView() {
        let cases: [AccessError] = [
            .unauthenticated,
            .staleBootstrapToken,
            .deviceAccessExpired,
            .forbidden(reason: "not_a_member", message: "No access"),
            .tlsPinFailure,
            .engineUnreachable,
            .transport("x")
        ]
        for error in cases {
            // A concrete action (compiles/returns for every case — no fallthrough).
            _ = action(error)
            // The view is constructible for every case with a non-empty title/body.
            let view = LibraryAccessDeniedView(
                libraryName: "Marshall Diaries",
                error: error,
                identity: nil,
                onRetry: {},
                onSignIn: {},
                onResetPin: {}
            )
            #expect(view.error == error)
            #expect(!(error.errorDescription ?? "").isEmpty)
        }
    }
}
