import SwiftUI

extension WorkflowInspector {

    // MARK: - MCP Tools Section

    var mcpToolsSection: some View {
        VStack(spacing: 16) {
            // Header with load button
            HStack {
                Label("MCP Tools", systemImage: "server.rack")
                    .font(.headline)
                Spacer()
                Button {
                    Task { await loadIntoRegistry() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "square.and.arrow.down")
                        Text("Load into Registry")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(mcpTools.isEmpty)
                .help("Make MCP tools available for drag and drop")
            }

            if isLoadingMCPTools {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 100)
            } else if mcpTools.isEmpty {
                // No MCP tools available
                VStack(spacing: 12) {
                    Image(systemName: "server.rack")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("No MCP Tools")
                        .font(.headline)
                    Text("Configure MCP servers to load tools")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Open MCP Servers") {
                        appState.showMCPServers = true
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                // Show MCP tools grouped by server
                ForEach(Array(mcpToolsGrouped.keys.sorted()), id: \.self) { serverName in
                    if let tools = mcpToolsGrouped[serverName] {
                        mcpServerToolsView(serverName: serverName, tools: tools)
                    }
                }
            }
        }
    }

    // MARK: - MCP Server Tools View

    @ViewBuilder
    func mcpServerToolsView(serverName: String, tools: [MCPToolInfo]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "server.rack")
                    .font(.caption)
                    .foregroundColor(.accentColor)
                Text(serverName)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Text("\(tools.count)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(Color(.controlBackgroundColor))
                    .cornerRadius(3)
            }
            .padding(.leading, 4)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 4) {
                ForEach(tools) { tool in
                    MCPToolBlockView(tool: tool)
                }
            }
        }
    }

}
