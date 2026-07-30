@testable import Fichero
import Testing

/// #3944: an app-managed embedded engine is the app's lifecycle/credential job,
/// not the user's. These pure predicates prove the view cannot render restart /
/// reset-sign-in / reset-certificate actions for that host class while preserving
/// the same actions for user-managed debug-local and remote/auth cases.
struct BackendConnectionActionPolicyTests {
    @Test func onlyReleaseEmbeddedIsAppManaged() {
        #expect(BackendConnectionView.usesAppManagedEmbeddedEngine(.releaseEmbedded))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.debugExternal))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.configuredRemote))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.iosCompanion))
        #expect(!BackendConnectionView.usesAppManagedEmbeddedEngine(.inert))
    }

    @Test func appManagedEmbeddedEngineShowsNoUserRemedyButtons() {
        for error in [AccessError.engineUnreachable, .staleBootstrapToken, .unauthenticated, .tlsPinFailure] {
            #expect(!BackendConnectionView.showsRetryButton(usesAppManagedEmbeddedEngine: true))
            #expect(!BackendConnectionView.showsResetSignInButton(
                accessError: error,
                usesAppManagedEmbeddedEngine: true
            ))
            #expect(!BackendConnectionView.showsResetCertificateButton(
                accessError: error,
                usesAppManagedEmbeddedEngine: true
            ))
        }
    }

    @Test func remoteAndDebugLocalKeepRetryOrAuthRemedies() {
        #expect(BackendConnectionView.showsRetryButton(usesAppManagedEmbeddedEngine: false))
        #expect(BackendConnectionView.showsResetSignInButton(
            accessError: .unauthenticated,
            usesAppManagedEmbeddedEngine: false
        ))
        #expect(BackendConnectionView.showsResetCertificateButton(
            accessError: .tlsPinFailure,
            usesAppManagedEmbeddedEngine: false
        ))
    }

    @Test func inappropriateRemoteRemediesStayHidden() {
        #expect(!BackendConnectionView.showsResetSignInButton(
            accessError: .forbidden(reason: "not_a_member", message: nil),
            usesAppManagedEmbeddedEngine: false
        ))
        #expect(!BackendConnectionView.showsResetCertificateButton(
            accessError: .engineUnreachable,
            usesAppManagedEmbeddedEngine: false
        ))
    }

    @Test func retryCopySeparatesDebugLocalFromRemote() {
        #expect(BackendConnectionView.retryButtonTitle(
            accessError: .engineUnreachable,
            usesExternalBackendConnection: false
        ) == "Start External Server")
        #expect(BackendConnectionView.retryButtonTitle(
            accessError: .engineUnreachable,
            usesExternalBackendConnection: true
        ) == "Retry Connection")
        #expect(BackendConnectionView.retryButtonTitle(
            accessError: .staleBootstrapToken,
            usesExternalBackendConnection: true
        ) == "Retry After Restarting Server")
    }
}
