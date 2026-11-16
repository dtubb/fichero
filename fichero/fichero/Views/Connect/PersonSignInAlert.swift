#if os(iOS) || os(visionOS)
import SwiftUI

extension View {
    /// The phone's sign-in (`sharing.people.sign-in-without-a-code`, Step 8.9): a host with accounts asks who this device is,
    /// and the alert itself has the username and password fields. Shown while `host` is set; the password lives only in this
    /// alert and the one pairing call it starts, never stored.
    func personSignInAlert(host: Binding<String?>, onSignIn: @escaping (PairingPerson) -> Void) -> some View {
        modifier(PersonSignInAlert(host: host, onSignIn: onSignIn))
    }
}

private struct PersonSignInAlert: ViewModifier {
    @Binding var host: String?
    let onSignIn: (PairingPerson) -> Void
    @State private var name = ""
    @State private var password = ""

    func body(content: Content) -> some View {
        let context = PairingFailure.Context(host: host ?? "your Mac", noun: RemoteClientPairingError.deviceNoun)
        content.alert(
            SharingFailurePrompt.title(.personRequired, context),
            isPresented: Binding(get: { host != nil }, set: { if !$0 { host = nil } })
        ) {
            TextField("Username", text: $name)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.username)
            SecureField("Password", text: $password)
                .textContentType(.password)
            Button("Sign In") {
                let person = PairingPerson(username: name, password: password)
                password = ""
                if let person { onSignIn(person) }
            }
            .disabled(PairingPerson(username: name, password: password) == nil)
            Button("Cancel", role: .cancel) { password = "" }
        } message: {
            Text(LocalNetworkPolicy.sentence(for: .personRequired, context: context))
        }
    }
}
#endif
