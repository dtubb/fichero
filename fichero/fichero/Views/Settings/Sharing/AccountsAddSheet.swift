import FicheroAPIClient
import SwiftUI

/// The `+` in Settings › Accounts (`sharing.settings.accounts-add-sheet`, #5928): Full name, Username, then a Password or a
/// Send invite link, and Owner. The words and rules are `AccountsAddSheetModel`.
struct AccountsAddSheet: View {
    let store: UsersStore
    /// The invite choice is there only while Multi-user is on.
    let multiUserOn: Bool
    let done: () -> Void

    @State private var fullName = ""
    @State private var username = ""
    @State private var way = AccountsAddSheetModel.Way.password
    @State private var password = ""
    @State private var isOwner = false
    @State private var isWorking = false
    @State private var failure: String?
    @State private var minted: MintedInvite?

    private var problem: String? {
        failure ?? AccountsAddSheetModel.problem(name: fullName, username: username, way: way, password: password)
    }

    var body: some View {
        VStack(spacing: 12) {
            Form {
                TextField("Full name", text: $fullName)
                    .textContentType(.name)
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .autocorrectionDisabled()
                if AccountsAddSheetModel.offersInvite(multiUserOn: multiUserOn) {
                    Picker("", selection: $way) {
                        Text("Password").tag(AccountsAddSheetModel.Way.password)
                        Text("Send invite link").tag(AccountsAddSheetModel.Way.invite)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }
                if way == .password {
                    SecureField("Password", text: $password)
                        .textContentType(.newPassword)
                }
                if AccountsAddSheetModel.asksOwner(way: way) {
                    Toggle("Owner", isOn: $isOwner)
                }
                if let problem {
                    Text(problem).font(.caption).foregroundStyle(failure == nil ? Color.secondary : Color.red)
                }
            }
            .formStyle(.grouped)
            HStack {
                Spacer()
                Button("Cancel", action: done).keyboardShortcut(.cancelAction)
                Button(AccountsAddSheetModel.buttonTitle(way: way, isWorking: isWorking)) { Task { await submit() } }
                    .keyboardShortcut(.defaultAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(!AccountsAddSheetModel.canSubmit(
                        name: fullName, username: username, way: way, password: password, isWorking: isWorking))
            }
        }
        .padding()
        .frame(minWidth: 380)
        .onChange(of: fullName) { _, _ in failure = nil }
        .onChange(of: username) { _, _ in failure = nil }
        // The link is handed over once it is made; the sheet closes when its own Done is pressed.
        .sheet(item: $minted, onDismiss: done) { InviteLinkSheet(mint: $0.mint) }
    }

    @MainActor
    private func submit() async {
        isWorking = true
        failure = nil
        defer { isWorking = false }
        let name = fullName.trimmingCharacters(in: .whitespaces)
        let user = username.trimmingCharacters(in: .whitespaces)
        do {
            switch way {
            case .password:
                try await store.createUser(username: user, displayName: name, password: password, isOwner: isOwner)
                done()
            case .invite:
                minted = MintedInvite(mint: try await store.createInvite(username: user, displayName: name))
            }
        } catch {
            failure = AccountsAddSheetModel.failureWords(error.localizedDescription)
        }
    }
}
