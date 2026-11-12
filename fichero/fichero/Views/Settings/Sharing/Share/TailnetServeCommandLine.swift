import SwiftUI

/// The one command that publishes this Mac on its tailnet, to paste in Terminal (`sharing.tailnet-serve-command-on-the-sheet`,
/// #5317, #6554): the sandboxed engine cannot run the Tailscale CLI, so it names the command instead. Nothing when the engine
/// has none to give (the forward is already Fichero's, or no tailnet name is known).
struct TailnetServeCommandLine: View {
    let command: String?

    var body: some View {
        if let command {
            VStack(alignment: .leading, spacing: 2) {
                Text("To share over Tailscale, run once in Terminal:")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    Text(command)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                    Button("Copy") { PlatformPasteboard.writeString(command) }
                        .controlSize(.small)
                }
            }
            .accessibilityIdentifier("sharing.address.serve-command")
        }
    }
}

#Preview("Serve command") {
    TailnetServeCommandLine(command: "tailscale serve --bg --https=8765 https+insecure://127.0.0.1:8765")
        .padding()
}
