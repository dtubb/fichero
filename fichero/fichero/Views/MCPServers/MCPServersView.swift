import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MCPServersView")

/// MCP Servers management view - manage MCP servers and their tools
struct MCPServersView: View {
    @Environment(MCPService.self) var mcpService
    @State private var servers: [MCPServerResponse] = []
    @State private var isLoading = true
    @State private var showAddServer = false
    @State private var selectedServer: MCPServerResponse?

    @AppStorage("window.listColumnWidth")
    private var listColumnWidth: Double = 280

    var body: some View {
        PlatformHSplitView {
            // Server list (left)
            VStack(alignment: .leading, spacing: 0) {
                List(selection: $selectedServer) {
                    ForEach(servers) { server in
                        MCPServerRow(server: server)
                            .tag(server)
                    }
                }
                .listStyle(.sidebar)

                Divider()

                // Add/Remove buttons
                HStack(spacing: 4) {
                    Button {
                        showAddServer = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .buttonStyle(.borderless)
                    .help("Add MCP Server")

                    Button(action: deleteSelectedServer) {
                        Image(systemName: "minus")
                    }
                    .buttonStyle(.borderless)
                    .disabled(selectedServer == nil)
                    .help("Remove Selected Server")

                    Spacer()

                    // Refresh button
                    Button {
                        Task { await loadServers() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.borderless)
                    .help("Refresh Server List")
                }
                .padding(8)
            }
            .frame(minWidth: 200, idealWidth: listColumnWidth, maxWidth: 420)

            // Server details (right)
            if let server = selectedServer {
                MCPServerDetailView(
                    server: server,
                    onUpdate: loadServers
                )
            } else {
                ContentUnavailableView(
                    "No Server Selected",
                    systemImage: "server.rack",
                    description: Text("Select an MCP server to view its configuration and tools.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadServers()
        }
        .sheet(isPresented: $showAddServer) {
            AddMCPServerSheet(onAdd: loadServers)
        }
    }

    private func loadServers() async {
        isLoading = true
        defer { isLoading = false }

        do {
            servers = try await mcpService.listServers()
        } catch {
            logger.error("Failed to load MCP servers: \(String(describing: error))")
        }
    }

    private func deleteSelectedServer() {
        guard let server = selectedServer else { return }
        Task {
            do {
                try await mcpService.deleteServer(server.id)
                selectedServer = nil
                await loadServers()
            } catch {
                logger.error("Delete failed: \(String(describing: error))")
            }
        }
    }
}

/// MCP Server row in the list
struct MCPServerRow: View {
    let server: MCPServerResponse

    var body: some View {
        HStack(spacing: 10) {
            // Server icon
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(server.color.opacity(0.15))
                    .frame(width: 28, height: 28)

                Image(systemName: server.icon)
                    .font(.caption)
                    .foregroundColor(server.color)
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(server.name)
                    .font(.body)

                Text(server.transportDisplayName)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Status indicator
            Circle()
                .fill(server.enabled ? Color.green : Color.gray)
                .frame(width: 8, height: 8)
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    MCPServersView()
        .environment(appState.mcpService)
        .frame(width: 900, height: 600)
}
