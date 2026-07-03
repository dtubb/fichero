import SwiftUI

/// Sheet wrapper for MCP Servers management view
struct MCPServersSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            MCPServersView()
                .navigationTitle("MCP Servers")
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                // Single native Done action in the toolbar instead of a
                // hand-rolled header close + footer button (#2806).
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 900, height: 600)
        #endif
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    MCPServersSheet()
        .environmentObject(appState)
        .environmentObject(appState.mcpService)
}
