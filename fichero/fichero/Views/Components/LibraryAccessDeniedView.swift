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
/// store's error classifies as an access failure (`AccessError.from`).
struct LibraryAccessDeniedView: View {
    let libraryName: String
    let error: AccessError
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

    /// The one next-step this denial resolves to, from error × identity.
    private enum PrimaryAction {
        case signIn, requestAccess, restartEngine, resetPin, retry
    }

    private var primaryAction: PrimaryAction {
        switch error {
        case .tlsPinFailure:
            return .resetPin
        case .engineUnreachable:
            return .restartEngine
        case .unauthenticated:
            return .signIn
        case .forbidden:
            // 401/403 collapse in some load paths — let identity disambiguate.
            if let identity, identity.identity != nil {
                if !identity.isAuthenticated { return .signIn }
                if identity.isOwnerAccess { return .restartEngine }
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
