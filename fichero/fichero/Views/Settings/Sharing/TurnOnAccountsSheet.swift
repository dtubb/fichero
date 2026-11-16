import SwiftUI

/// "Turn on accounts…" (`sharing.multiuser-off-says-so`): runs `AccountsOnSequence` against this Mac's engine. A password
/// field appears only when the owner has not chosen one; the 8-character rule is `NewPasswordRule`.
struct TurnOnAccountsSheet: View {
    @Environment(AppState.self) private var appState
    let store: UsersStore
    let identityStore: IdentityStore
    let done: () -> Void

    @State private var password = ""
    @State private var asksPassword = false
    @State private var isWorking = false
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(AccountsOnSequence.offSentence)
            if asksPassword {
                SecureField("Your password", text: $password)
                    .textContentType(.newPassword)
                Text(NewPasswordRule.hint).font(.caption).foregroundStyle(.secondary)
            }
            if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: done).disabled(isWorking)
                Button(isWorking ? "Turning on…" : "Turn On") { Task { await run() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(isWorking || (asksPassword && password.count < NewPasswordRule.minimumLength))
            }
        }
        .padding(20)
        .frame(minWidth: 380)
    }

    private func run() async {
        isWorking = true
        failure = nil
        defer { isWorking = false }
        let host = LiveAccountsOnHost(appState: appState, store: store, identityStore: identityStore)
        switch await AccountsOnSequence.run(host: host, password: asksPassword ? password : nil) {
        case .turnedOn: done()
        case .needsPassword:
            // Asking again with the field already showing would look like nothing happened: say what is wanted.
            if asksPassword { failure = NewPasswordRule.hint }
            asksPassword = true
        case .failed(let sentence): failure = sentence
        }
    }
}

/// This Mac's engine behind the sequence: the audited switch (`MultiuserSwitch`), the owner's local password call, then a re-read.
@MainActor
struct LiveAccountsOnHost: AccountsOnSequence.Host {
    let appState: AppState
    let store: UsersStore
    let identityStore: IdentityStore

    private var pairing: PairingService { PairingService(apiRoot: EngineConfig.host) }

    func blocker() async throws -> String? { try await pairing.sharingState().multiuserBlocker }

    func setOwnerPassword(_ password: String) async throws { try await store.setOwnerPassword(password) }

    func setMultiuser(_ enabled: Bool) async throws {
        do {
            try await MultiuserSwitch.set(enabled, pairing: pairing, service: nil, steps: nil)
        } catch APIError.httpError(let status, let message) {
            throw AccountsOnSequence.Refusal(status: status, detail: message)
        }
    }

    func reload() async {
        await appState.checkBackendHealth()
        await identityStore.load()
        await store.load()
    }
}

#Preview("Turn on accounts") {
    let appState = AppState()
    TurnOnAccountsSheet(store: appState.usersStore, identityStore: appState.identityStore, done: {})
        .environment(appState)
}
