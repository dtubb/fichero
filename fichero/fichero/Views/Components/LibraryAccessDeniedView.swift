import SwiftUI

/// In-content "you don't have access to <library>" state (F6).
///
/// The top invariant of the access work is *never a silent 403 or blank pane*: a
/// library read that comes back denied must land here, not on an empty list. It
/// answers three things at once — **which** library is blocked, **why** (the
/// typed `AccessError`'s message), and **who you are** (from `IdentityStore`) —
/// then offers exactly the next action that can unblock you: sign in, request
/// access from the owner, reset a mismatched certificate, or (when the library
/// is *yours* but the engine is refusing) restart the engine.
///
/// Rendered by `LibraryView` in place of the generic error state whenever the
/// store's error is an `AccessError`.
struct LibraryAccessDeniedView: View {
    let libraryName: String
    let error: AccessError
    /// Where the library lives on disk (C3). Shown under the reason because the
    /// engine's most common library denial is about the LOCATION — "Library path
    /// is not in an allowed location or not a .fichero package." names no path,
    /// so without this the user is told the place is wrong and not which place.
    /// Optional: a denial that has nothing to do with location omits it.
    var libraryPath: String?
    /// Who the current credential resolves to on this engine. Optional so the
    /// view still renders (with generic framing) if identity hasn't loaded.
    var identity: IdentityStore?
    /// Re-run the library load. Used by every "retry"-shaped action.
    var onRetry: (@MainActor () async -> Void)?
    /// Present the sign-in gate. Nil hides sign-in affordances (e.g. single-user).
    var onSignIn: (@MainActor () -> Void)?
    /// Clear the stored certificate pin so the next connect re-pins. Nil hides
    /// the reset-certificate affordance.
    var onResetPin: (@MainActor () -> Void)?
    /// Start the re-pair flow (scan a fresh QR on the Mac) for an expired/revoked
    /// device token (#3096). Nil hides the re-pair button.
    var onRePair: (@MainActor () -> Void)?

    /// The one next-step this denial resolves to, from error × identity.
    /// The concrete next-action a denial resolves to. Internal (not private) so
    /// the decision can be unit-tested for every failure case without rendering.
    enum PrimaryAction: Equatable {
        case signIn, requestAccess, restartEngine, resetPin, rePair, retry
    }

    private var primaryAction: PrimaryAction {
        let hasIdentity = identity?.identity != nil
        return Self.resolvePrimaryAction(
            for: error,
            isAuthenticated: hasIdentity ? identity?.isAuthenticated : nil,
            isOwnerAccess: identity?.isOwnerAccess ?? false
        )
    }

    /// Pure decision: failure × identity → the one next action. Extracted so the
    /// "right next-action for EACH case" invariant is testable. `isAuthenticated`
    /// is `nil` when identity hasn't loaded (can't disambiguate a bare forbidden).
    static func resolvePrimaryAction(
        for error: AccessError,
        isAuthenticated: Bool?,
        isOwnerAccess: Bool
    ) -> PrimaryAction {
        switch error {
        case .tlsPinFailure:
            return .resetPin
        case .engineUnreachable, .staleBootstrapToken:
            // A stale bootstrap token can only be fixed by the engine re-minting
            // it — restart is the honest next step, not sign-in.
            return .restartEngine
        case .deviceAccessExpired:
            // A device has no password sign-in; re-pairing is the only recovery.
            return .rePair
        case .unauthenticated:
            return .signIn
        case .forbidden:
            // 401/403 collapse in some load paths — let identity disambiguate.
            if let isAuthenticated {
                if !isAuthenticated { return .signIn }
                if isOwnerAccess { return .restartEngine }
            }
            return .requestAccess
        case .transport:
            return .retry
        }
    }

    private var symbol: String {
        switch error {
        case .tlsPinFailure: return "lock.trianglebadge.exclamationmark"
        case .engineUnreachable, .transport: return "bolt.horizontal.circle"
        case .staleBootstrapToken: return "key.slash"
        case .deviceAccessExpired: return "iphone.slash"
        case .unauthenticated, .forbidden: return "lock.slash"
        }
    }

    /// "Signed in as …", or the single-user / not-signed-in framing.
    private var whoText: String? {
        guard let identity, identity.identity != nil else { return nil }
        if let name = identity.displayName { return "Signed in as \(name)." }
        if !identity.multiuserEnabled { return "Using this Mac's engine credentials." }
        return "You're not signed in."
    }

    var body: some View {
        ContentUnavailableView {
            Label("No Access to \(libraryName)", systemImage: symbol)
        } description: {
            VStack(spacing: 6) {
                Text(error.errorDescription ?? "You don't have access to this library.")
                if let libraryPath {
                    Text(libraryPath)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .lineLimit(3)
                        .truncationMode(.middle)
                }
                if let whoText {
                    Text(whoText)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
        } actions: {
            actionButtons
        }
    }

    @ViewBuilder
    private var actionButtons: some View {
        switch primaryAction {
        case .signIn:
            if let onSignIn {
                Button("Sign In") { onSignIn() }
                    .buttonStyle(.borderedProminent)
            }
            retryButton(title: "Try Again")

        case .requestAccess:
            // Nothing the app can do for you here — the owner must grant access.
            // Be explicit about that, then offer to switch accounts / retry.
            Text("Ask this library's owner to grant you access, then try again.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if let onSignIn {
                Button("Sign in as a Different User") { onSignIn() }
                    .buttonStyle(.borderedProminent)
            }
            retryButton(title: "Try Again")

        case .restartEngine:
            // Owner blocked / engine refusing: this is the "it's yours — restart"
            // path. Retry re-runs the load once the engine recovers.
            retryButton(title: "Try Again", prominent: true)

        case .resetPin:
            if let onResetPin {
                Button("Reset Certificate & Retry") {
                    onResetPin()
                    Task { await onRetry?() }
                }
                .buttonStyle(.borderedProminent)
            } else {
                retryButton(title: "Try Again", prominent: true)
            }

        case .rePair:
            // Expired/revoked device: re-pair is the only recovery (no password
            // sign-in for a device). Retry stays as a secondary in case the host
            // recovered (e.g. a transient blip misread as expiry).
            if let onRePair {
                Button("Re-pair This Device") { onRePair() }
                    .buttonStyle(.borderedProminent)
            }
            retryButton(title: "Try Again")

        case .retry:
            retryButton(title: "Try Again", prominent: true)
        }
    }

    @ViewBuilder
    private func retryButton(title: String, prominent: Bool = false) -> some View {
        let button = Button(title) { Task { await onRetry?() } }
            .keyboardShortcut("r", modifiers: .command)
        if prominent {
            button.buttonStyle(.borderedProminent)
        } else {
            button.buttonStyle(.bordered)
        }
    }
}

#Preview("Forbidden") {
    LibraryAccessDeniedView(
        libraryName: "Marshall Diaries",
        error: .forbidden(reason: "not_a_member", message: "You don't have access to this library."),
        identity: nil,
        onRetry: {},
        onSignIn: {},
        onResetPin: {}
    )
    .frame(width: 500, height: 360)
}

#Preview("TLS pin") {
    LibraryAccessDeniedView(
        libraryName: "Archivos Neustros",
        error: .tlsPinFailure,
        identity: nil,
        onRetry: {},
        onSignIn: nil,
        onResetPin: {}
    )
    .frame(width: 500, height: 360)
}
