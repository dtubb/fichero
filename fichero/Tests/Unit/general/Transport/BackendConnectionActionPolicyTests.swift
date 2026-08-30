@testable import Fichero
import Testing

/// #3944 + #4380: which recovery the connection surface offers is a pure
/// function of the engine phase, who owns the engine process, and the
/// classified access error — never of who happens to be rendering.
///
/// #3944's rule survives in a sharper form: an app-managed embedded engine
/// mints its own credentials and pins its own certificate, so it must never
/// offer to reset either. What #4380 changes is the *positive* case — it now
/// offers "Restart Engine", because the app owns the process and restarting it
/// is a real thing the app can do, where the old copy offered a shell command
/// under a label truncated to "Start Exte…".
struct BackendConnectionActionPolicyTests {
    private typealias Ownership = ConnectionPresentation.EngineOwnership

    @Test func onlyReleaseEmbeddedIsAppManaged() {
        #expect(BackendConnectionView.usesAppManagedEmbeddedEngine(.releaseEmbedded))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.debugExternal))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.configuredRemote))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.iosCompanion))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.inert))
    }

    @Test func ownershipFollowsProvisioningStrategy() {
        #expect(Ownership.resolve(.releaseEmbedded) == .appManaged)
        #expect(Ownership.resolve(.debugExternal) == .externalLocal)
        #expect(Ownership.resolve(.inert) == .externalLocal)
        #expect(Ownership.resolve(.configuredRemote) == .remote)
        #expect(Ownership.resolve(.iosCompanion) == .remote)
    }

    @Test func appManagedEngineNeverOffersSignInOrCertificateResets() {
        for error in [AccessError.engineUnreachable, .staleBootstrapToken, .unauthenticated, .tlsPinFailure] {
            let action = ConnectionPresentation.failureAction(
                accessError: error,
                authBroken: false,
                ownership: .appManaged
            )
            #expect(action != .resetSignIn)
            #expect(action != .resetCertificate)
            // It always offers the one thing it CAN do.
            #expect(action == .restartEngine)
        }
    }

    @Test func userManagedEnginesKeepTheirAuthRemedies() {
        #expect(ConnectionPresentation.failureAction(
            accessError: .unauthenticated,
            authBroken: true,
            ownership: .remote
        ) == .resetSignIn)
        #expect(ConnectionPresentation.failureAction(
            accessError: .tlsPinFailure,
            authBroken: false,
            ownership: .remote
        ) == .resetCertificate)
        #expect(ConnectionPresentation.failureAction(
            accessError: .deviceAccessExpired,
            authBroken: false,
            ownership: .remote
        ) == .forgetPairing)
    }

    @Test func inappropriateRemediesStayHidden() {
        // A scoped 403 is not fixed by signing in again, and nothing the app
        // can do mints authorization — so it offers nothing rather than
        // something that cannot work.
        #expect(ConnectionPresentation.failureAction(
            accessError: .forbidden(reason: "not_a_member", message: nil),
            authBroken: false,
            ownership: .remote
        ) == nil)
        #expect(ConnectionPresentation.failureAction(
            accessError: .forbidden(reason: "not_a_member", message: nil),
            authBroken: false,
            ownership: .appManaged
        ) == nil)
        // An unreachable engine is not a certificate problem.
        #expect(ConnectionPresentation.failureAction(
            accessError: .engineUnreachable,
            authBroken: false,
            ownership: .externalLocal
        ) == .reconnect)
    }

    /// The regression this issue is named for: the primary label used to be
    /// "Start External Server", which the popover rendered as "Start Exte…".
    @Test func primaryActionLabelsAreShortAndNeverPrescribeACommand() {
        for action in [
            ConnectionPresentation.Action.reconnect,
            .restartEngine,
            .resolvePortConflict,
            .resetSignIn,
            .resetCertificate,
            .forgetPairing
        ] {
            #expect(action.title.count <= ConnectionPresentation.labelBudget)
            #expect(!action.title.isEmpty)
            #expect(!action.title.contains("Start External Server"))
            #expect(!action.systemImage.isEmpty)
        }
    }
}
