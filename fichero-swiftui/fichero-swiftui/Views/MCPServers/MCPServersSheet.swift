import SwiftUI

/// Sheet wrapper for MCP Servers management view
struct MCPServersSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("MCP Servers")
                    .font(.title)
                    .fontWeight(.semibold)
                Spacer()
                Button(action: { dismiss() }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                        .imageScale(.large)
                }
                .buttonStyle(.plain)
            }
            .padding()

            Divider()

            // Main content
            MCPServersView()

            Divider()

            // Footer
            HStack {
                Spacer()
                Button("Done") {
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
            }
            .padding()
        }
        .frame(width: 900, height: 600)
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    MCPServersSheet()
        .environmentObject(appState)
        .environmentObject(appState.mcpService)
}
