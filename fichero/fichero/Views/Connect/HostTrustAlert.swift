import SwiftUI

extension View {
    /// The first-contact ask for a typed address (`sharing.people.sign-in-without-a-code`): the host's key fingerprint, to
    /// compare with the host's Sharing pane, then Trust and Connect or Cancel. Shown while `ask` is set; the Mac and the phone
    /// both use it.
    func hostTrustAlert(_ ask: Binding<HostKeyFingerprint.Ask?>, onTrust: @escaping (HostKeyFingerprint.Ask) -> Void) -> some View {
        alert(ask.wrappedValue.map { "Trust \($0.url.host ?? "this Mac")?" } ?? "",
              isPresented: Binding(get: { ask.wrappedValue != nil }, set: { if !$0 { ask.wrappedValue = nil } }),
              presenting: ask.wrappedValue) { shown in
            Button("Trust and Connect") { onTrust(shown) }
            Button("Cancel", role: .cancel) {}
        } message: { shown in
            Text(HostKeyFingerprint.trustSentence(host: shown.url.host ?? "", fingerprint: shown.fingerprint))
        }
    }
}
