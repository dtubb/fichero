import SwiftUI

/// The login gate shown instead of the library when multi-user auth is on and
/// there is no valid session (EPIC #2021/#2022). Switches between the normal
/// sign-in form and the first-run "create owner" form based on the session
/// phase. Native SwiftUI, semantic fonts, `SecureField` for secrets; passwords
/// are held only in local `@State` and never logged.
struct AuthGateView: View {
    @Bindable var session: SessionStore

    var body: some View {
        Group {
            switch session.phase {
            case .needsOwnerSetup:
                OwnerSetupFormView(session: session)
            default:
                LoginFormView(session: session)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.background)
    }
}

/// Shared framing for the auth cards so login and owner-setup line up.
private struct AuthCard<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(spacing: 20) {
            VStack(spacing: 8) {
                Image(systemName: "lock.shield")
                    .font(.largeTitle)
                    .foregroundStyle(.secondary)
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

private struct OwnerSetupFormView: View {
    @Bindable var session: SessionStore

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
            && !displayName.trimmingCharacters(in: .whitespaces).isEmpty
            && password.count >= Self.minPasswordLength
            && passwordsMatch
            && !isSubmitting
    }

    var body: some View {
        AuthCard(
            title: "Create Owner Account",
            subtitle: "This is the first account on this server. It has owner access."
        ) {
            VStack(spacing: 12) {
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .textFieldStyle(.roundedBorder)
                    #if !os(macOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    #endif

                TextField("Display Name", text: $displayName)
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
