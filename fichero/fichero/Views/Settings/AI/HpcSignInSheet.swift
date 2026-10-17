import SwiftUI

/// Shows what the cluster asks while signing in (a second factor, a passphrase) and sends the answer on; nothing is
/// kept. The far side's own prompt text is shown as it came, so the person knows which credential is wanted.
struct HpcSignInSheet: View {
    let clusterId: String
    let clusterName: String
    @State var service: HpcSignInService
    @Environment(\.dismiss) private var dismiss
    @State private var answers: [String: String] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sign in to \(clusterName)").font(.title3)
            switch service.phase {
            case .idle, .signingIn:
                if service.prompts.isEmpty {
                    ProgressView("Connecting…")
                } else {
                    ForEach(service.prompts) { prompt in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(prompt.text).font(.body)
                            SecureField("Answer", text: binding(for: prompt))
                                .onSubmit { send(prompt) }
                            Text("For a push, approve it on your phone.").font(.caption).foregroundStyle(.secondary)
                            Button("Send") { send(prompt) }
                        }
                    }
                }
            case .signedIn:
                Text("Signed in. The connection stays open while you work.")
            case .failed(let why):
                Text(why).foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button(service.phase == .signedIn ? "Done" : "Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
        }
        .padding(20)
        .frame(minWidth: 380)
        .task { await service.signIn(clusterId: clusterId) }
    }

    private func binding(for prompt: HpcSignInService.Prompt) -> Binding<String> {
        Binding(get: { answers[prompt.id] ?? "" }, set: { answers[prompt.id] = $0 })
    }

    private func send(_ prompt: HpcSignInService.Prompt) {
        let text = answers[prompt.id] ?? ""
        answers[prompt.id] = nil
        Task { await service.answer(prompt, with: text) }
    }
}
