import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MCPServerDetailView")

/// MCP Server detail view showing configuration and loaded tools
struct MCPServerDetailView: View {
    let server: MCPServerResponse
    let onUpdate: () async -> Void

    @Environment(MCPService.self) var mcpService
    @State private var isLoadingTools = false
    @State private var loadedTools: [MCPToolInfo] = []
    @State private var loadError: String?

    var body: some View {
        ScrollView {
            Form {
                // Server Info Section
                Section("Server") {
                    LabeledContent("Name") {
                        Text(server.name)
                    }

                    LabeledContent("Transport") {
                        HStack {
                            Image(systemName: server.icon)
                                .foregroundColor(server.color)
                            Text(server.transportDisplayName)
                        }
                    }

                    LabeledContent("Status") {
                        HStack {
                            Circle()
                                .fill(server.enabled ? Color.green : Color.gray)
                                .frame(width: 8, height: 8)
                            Text(server.enabled ? "Enabled" : "Disabled")
                        }
                    }

                    if !server.description.isEmpty {
                        LabeledContent("Description") {
                            Text(server.description)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                // Connection Details Section
                Section("Connection") {
                    if server.needsCommand {
                        LabeledContent("Command") {
                            Text(server.command ?? "None")
                                .font(.system(.caption, design: .monospaced))
                        }

                        if !server.args.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Arguments")
                                    .font(.caption)
                                    .foregroundColor(.secondary)

                                ForEach(Array(server.args.enumerated()), id: \.offset) { _, arg in
                                    Text("• \(arg)")
                                        .font(.system(.caption2, design: .monospaced))
                                        .foregroundColor(.secondary)
                                }
                            }
                        }

                        if !server.env.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Environment")
                                    .font(.caption)
                                    .foregroundColor(.secondary)

                                ForEach(Array(server.env.keys.sorted()), id: \.self) { key in
                                    if let value = server.env[key] {
                                        Text("\(key)=\(value)")
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }
                    }

                    if server.needsURL {
                        LabeledContent("URL") {
                            Text(server.url ?? "None")
                                .font(.system(.caption, design: .monospaced))
                        }

                        if !server.headers.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Headers")
                                    .font(.caption)
                                    .foregroundColor(.secondary)

                                ForEach(Array(server.headers.keys.sorted()), id: \.self) { key in
                                    if let value = server.headers[key] {
                                        Text("\(key): \(value)")
                                            .font(.system(.caption2, design: .monospaced))
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                        }
                    }

                    LabeledContent("Tool Name Prefix") {
                        Text(server.toolNamePrefix ? "Enabled" : "Disabled")
                    }
                }

                // Tools Section
                Section {
                    if isLoadingTools {
                        ProgressView("Loading tools...")
                    } else if let error = loadError {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(.orange)
                                Text("Failed to load tools")
                                    .font(.body)
                            }

                            Text(error)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .fixedSize(horizontal: false, vertical: true)

                            Button("Retry") {
                                Task { await loadTools() }
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    } else if loadedTools.isEmpty {
                        Text("No tools loaded")
                            .foregroundColor(.secondary)
                    } else {
                        ForEach(loadedTools) { tool in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tool.name)
                                    .font(.body)
                                    .font(.system(.body, design: .monospaced))

                                if !tool.description.isEmpty {
                                    Text(tool.description)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                } header: {
                    HStack {
                        Text("Tools (\(loadedTools.count))")
                        Spacer()

                        if !isLoadingTools && loadError == nil {
                            Button {
                                Task { await loadTools(forceReload: true) }
                            } label: {
                                Image(systemName: "arrow.clockwise")
                            }
                            .buttonStyle(.plain)
                            .help("Reload Tools")
                            .accessibilityLabel("Reload Tools")
                        }
                    }
                }
            }
            .padding()
        }
        .task(id: server.id) {
            // Load tools when server changes
            await loadTools()
        }
    }

    private func loadTools(forceReload: Bool = false) async {
        if !server.enabled {
            loadedTools = []
            loadError = "Server is disabled"
            return
        }

        isLoadingTools = true
        loadError = nil
        defer { isLoadingTools = false }

        do {
            let response = try await mcpService.loadServerTools(server.id, forceReload: forceReload)
            loadedTools = response.tools
        } catch {
            loadError = error.localizedDescription
            logger.error("Failed to load tools: \(String(describing: error))")
        }
    }
}
