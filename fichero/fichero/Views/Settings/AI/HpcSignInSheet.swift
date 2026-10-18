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
        VStack(alignment: .leading, spacing: 0) {
            Text("Sign In to \(clusterName)")
                .font(.headline)
                .padding()
            Divider()
            VStack(alignment: .leading, spacing: 12) {
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
                                if Self.asksForAPush(prompt.text) {
                                    Text("For a push, approve it on your phone.").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                case .signedIn:
                    Label("Signed in. The connection stays open while you work.", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                case .failed(let why):
                    Label(why, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            Divider()
            HStack {
                Button(service.phase == .signedIn ? "Done" : "Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                if service.phase != .signedIn, let prompt = service.prompts.first {
                    Button("Send") { send(prompt) }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding()
        }
        .frame(width: 400)
        .task { await service.signIn(clusterId: clusterId) }
    }

    /// Only a Duo-style prompt offers the phone; a passphrase or a one-time code does not.
    static func asksForAPush(_ text: String) -> Bool {
        let lower = text.lowercased()
        return lower.contains("duo") || lower.contains("push")
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

#Preview("Waiting for the second factor") {
    let appState = AppState()
    let prompt = HpcSignInService.Prompt(id: "1", text: "Duo passcode or option (1-3): ")
    HpcSignInSheet(
        clusterId: "rorqual", clusterName: "Rorqual",
        service: HpcSignInService.previewing(prompts: [prompt], phase: .signingIn, in: appState))
}
