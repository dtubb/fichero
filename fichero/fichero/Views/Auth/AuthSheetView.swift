#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

/// The multi-user sign-in surface (EPIC #2021/#2022), presented as CHROME —
/// a modal sheet on macOS (a full-screen cover on iOS, an explicit platform
/// decision in `ContentView`) — never as a view that replaces the window
/// (#4359: the full-window `AuthGateView` takeover is deleted; the window
/// keeps its shell, sidebar and content while this sheet is up). Switches
/// between the normal sign-in form and the first-run "create owner" form
/// based on the session phase. Native SwiftUI, semantic fonts, `SecureField`
/// for secrets; passwords are held only in local `@State` and never logged.
///
/// Presented only for a RESOLVED gate (`requiresAuthUI` / a pending invite);
/// `.checking` — including failed probes — must present nothing (#4348 class:
/// failure is "unknown", never "signed out").
struct AuthSheetView: View {
    @Bindable var session: SessionStore
    /// User chose "Set up an owner account" from the sign-in form (#3331) — show
    /// owner setup even though accounts exist (they just can't sign in).
    @State private var showOwnerSetup = false

    var body: some View {
        Group {
            if session.pendingInviteToken != nil {
                // An invite link was opened (#3157) — the invitee sets a
                // password to claim the account, ahead of the normal gate.
                RedeemInviteFormView(session: session)
            } else {
                switch session.phase {
                case .needsOwnerSetup:
                    // First run — no accounts exist; owner setup is the only path.
                    OwnerSetupFormView(session: session, onBackToSignIn: nil)
                default:
                    if showOwnerSetup {
                        OwnerSetupFormView(session: session, onBackToSignIn: { showOwnerSetup = false })
                    } else {
                        LoginFormView(session: session, onCreateOwner: { showOwnerSetup = true })
                    }
                }
            }
        }
        .padding()
        .presentationBackground(.background)
    }
}

/// Shared framing for the auth cards so login and owner-setup line up.
private struct AuthCard<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    /// The app's flat icon, loaded from AppIcon.icns at the bundle root so it
    /// shows the real Fichero mark without the system squircle
    /// NSApp.applicationIconImage applies (mirrors BackendConnectionView, #3331).
    static var ficheroIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath,
           let image = PlatformImage(contentsOfFile: "\(resourcePath)/AppIcon.icns") {
            return image
        }
        #if canImport(AppKit)
        return NSApp.applicationIconImage ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "books.vertical") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }

    var body: some View {
        VStack(spacing: 20) {
            VStack(spacing: 8) {
                Image(platformImage: Self.ficheroIconImage)
                    .resizable()
                    .frame(width: 64, height: 64)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.title2)
                    .fontWeight(.semibold)
                Text(subtitle)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            content
        }
        .padding(28)
        .frame(maxWidth: 360)
    }
}

private struct LoginFormView: View {
    @Bindable var session: SessionStore
    /// Switch to the owner-setup form so a user who can't sign in (no usable
    /// owner credential) can create/claim the owner account instead of being
    /// walled (#3331).
    var onCreateOwner: () -> Void

    @State private var username = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isSubmitting = false

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty
            && !password.isEmpty
            && !isSubmitting
    }

    var body: some View {
        AuthCard(title: "Sign In", subtitle: "Sign in to open your libraries.") {
            VStack(spacing: 12) {
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .textFieldStyle(.roundedBorder)
                    #if !os(macOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    #endif
                    .onSubmit(submit)

                SecureField("Password", text: $password)
                    .textContentType(.password)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(submit)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Sign In").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!canSubmit)
                .keyboardShortcut(.defaultAction)

                Button("Set up an owner account", action: onCreateOwner)
                    .buttonStyle(.plain)
                    .font(.callout)
                    .foregroundStyle(Color.accentColor)
                    .disabled(isSubmitting)
            }
        }
    }

    private func submit() {
        guard canSubmit else { return }
        errorMessage = nil
        isSubmitting = true
        let enteredUsername = username
        let enteredPassword = password
        Task {
            defer { isSubmitting = false }
            do {
                try await session.login(username: enteredUsername, password: enteredPassword)
                password = ""
            } catch {
                errorMessage = error.localizedDescription
                password = ""
            }
        }
    }
}

/// Invitee side of the account-sharing flow (#3157): a `fichero://invite`
/// link was opened, so the person sets *only* a new password to claim the
/// account the owner pre-named. Success drops them into a signed-in session.
private struct RedeemInviteFormView: View {
    @Bindable var session: SessionStore

    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var isSubmitting = false

    private static let minPasswordLength = 8

    private var passwordsMatch: Bool { password == confirmPassword }

    private var canSubmit: Bool {
        password.count >= Self.minPasswordLength
            && passwordsMatch
            && !isSubmitting
    }

    var body: some View {
        AuthCard(
            title: "Accept Invitation",
            subtitle: "You've been invited to this library. Choose a password to finish setting up your account."
        ) {
            VStack(spacing: 12) {
                SecureField("Password", text: $password)
                    .textContentType(.newPassword)
                    .textFieldStyle(.roundedBorder)

                SecureField("Confirm Password", text: $confirmPassword)
                    .textContentType(.newPassword)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(submit)

                if let hint = validationHint {
                    Text(hint)
                        .font(.caption)
                        .foregroundStyle(errorMessage == nil ? Color.secondary : Color.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Accept & Sign In").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!canSubmit)
                .keyboardShortcut(.defaultAction)

                Button("Cancel") { session.cancelInviteRedemption() }
                    .buttonStyle(.borderless)
                    .disabled(isSubmitting)
            }
        }
    }

    private var validationHint: String? {
        if let errorMessage { return errorMessage }
        if !password.isEmpty, password.count < Self.minPasswordLength {
            return "Password must be at least \(Self.minPasswordLength) characters."
        }
        if !confirmPassword.isEmpty, !passwordsMatch {
            return "Passwords don't match."
        }
        return nil
    }

    private func submit() {
        guard canSubmit else { return }
        errorMessage = nil
        isSubmitting = true
        let enteredPassword = password
        Task {
            defer { isSubmitting = false }
            do {
                try await session.redeemInvite(newPassword: enteredPassword)
                password = ""
                confirmPassword = ""
            } catch {
                errorMessage = error.localizedDescription
                password = ""
                confirmPassword = ""
            }
        }
    }
}

private struct OwnerSetupFormView: View {
    @Bindable var session: SessionStore
    /// Present when reached from the sign-in form (#3331); nil on first-run where
    /// there's nothing to sign in to.
    var onBackToSignIn: (() -> Void)?

    @State private var username = ""
    @State private var displayName = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var isSubmitting = false

    private static let minPasswordLength = 8

    private var passwordsMatch: Bool { password == confirmPassword }

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty
            && password.count >= Self.minPasswordLength
            && passwordsMatch
            && !isSubmitting
    }

    var body: some View {
        AuthCard(
            title: "Create Owner Account",
            subtitle: onBackToSignIn == nil
                ? "This is the first account on this server. It has owner access."
                : "Set up an owner account with owner access to this server."
        ) {
            VStack(spacing: 12) {
                TextField("Username / handle", text: $username)
                    .textContentType(.username)
                    .textFieldStyle(.roundedBorder)
                    #if !os(macOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    #endif

                TextField("Display name (optional)", text: $displayName)
                    .textContentType(.name)
                    .textFieldStyle(.roundedBorder)

                SecureField("Password", text: $password)
                    .textContentType(.newPassword)
                    .textFieldStyle(.roundedBorder)

                SecureField("Confirm Password", text: $confirmPassword)
                    .textContentType(.newPassword)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(submit)

                if let hint = validationHint {
                    Text(hint)
                        .font(.caption)
                        .foregroundStyle(errorMessage == nil ? Color.secondary : Color.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    if isSubmitting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Create Account").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!canSubmit)
                .keyboardShortcut(.defaultAction)

                if let onBackToSignIn {
                    Button("Back to Sign In", action: onBackToSignIn)
                        .buttonStyle(.plain)
                        .font(.callout)
                        .foregroundStyle(Color.accentColor)
                        .disabled(isSubmitting)
                }
            }
        }
    }

    /// Live guidance (secondary) or the submit error (red). Never echoes the
    /// password itself.
    private var validationHint: String? {
        if let errorMessage { return errorMessage }
        if !password.isEmpty, password.count < Self.minPasswordLength {
            return "Password must be at least \(Self.minPasswordLength) characters."
        }
        if !confirmPassword.isEmpty, !passwordsMatch {
            return "Passwords don't match."
        }
        return nil
    }

    private func submit() {
        guard canSubmit else { return }
        errorMessage = nil
        isSubmitting = true
        let enteredUsername = username
        let enteredDisplayName = displayName
        let enteredPassword = password
        Task {
            defer { isSubmitting = false }
            do {
                try await session.createOwner(
                    username: enteredUsername,
                    displayName: enteredDisplayName,
                    password: enteredPassword
                )
                password = ""
                confirmPassword = ""
            } catch {
                errorMessage = error.localizedDescription
                password = ""
                confirmPassword = ""
            }
        }
    }
}
