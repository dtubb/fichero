import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MCPToolsCatalogView")

/// View showing all MCP tools from all servers
struct MCPToolsCatalogView: View {
    @Environment(MCPService.self) var mcpService
    @State private var tools: [MCPToolInfo] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var selectedServerFilter: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("MCP Tools Catalog")
                    .font(.title2)
                    .fontWeight(.semibold)

                Spacer()

                // Load to Workflow Registry button
                Button {
                    Task { await loadIntoWorkflowRegistry() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "square.and.arrow.down")
                        Text("Load to Workflow Registry")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(tools.isEmpty)
                .help("Make these tools available in the workflow editor")

                Button {
                    Task { await loadAllTools() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.borderless)
                .help("Refresh Tools")
                .accessibilityLabel("Refresh Tools")
            }
            .padding()

            Divider()

            // Search and filter bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search tools...", text: $searchText)
                    .textFieldStyle(.plain)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear tool search")
                }

                Divider()
                    .frame(height: 20)

                // Server filter
                Picker("Server", selection: $selectedServerFilter) {
                    Text("All Servers").tag(nil as String?)
                    ForEach(uniqueServerNames, id: \.self) { serverName in
                        Text(serverName).tag(serverName as String?)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 150)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(.regularMaterial)

            Divider()

            // Content
            if isLoading {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Loading tools...")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text("Failed to load tools")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") {
                        Task { await loadAllTools() }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredTools.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: searchText.isEmpty ? "wrench.and.screwdriver" : "magnifyingglass")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(searchText.isEmpty ? "No tools loaded" : "No tools found")
                        .font(.headline)
                    if searchText.isEmpty {
                        Text("Load tools from MCP servers to see them here")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Tools list grouped by server
                List {
                    ForEach(groupedTools, id: \.server) { group in
                        Section(header: serverHeader(group.server)) {
                            ForEach(group.tools) { tool in
                                MCPToolRow(tool: tool)
                            }
                        }
                    }
                }
                .listStyle(.inset)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadAllTools()
        }
    }

    @ViewBuilder
    private func serverHeader(_ serverName: String) -> some View {
        HStack {
            Image(systemName: "server.rack")
                .foregroundColor(.accentColor)
            Text(serverName)
                .font(.headline)
            Spacer()
            Text("\(groupedTools.first { $0.server == serverName }?.tools.count ?? 0) tools")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var uniqueServerNames: [String] {
        Array(Set(tools.map { $0.serverName })).sorted()
    }

    private var filteredTools: [MCPToolInfo] {
        var result = tools

        // Filter by server
        if let serverFilter = selectedServerFilter {
            result = result.filter { $0.serverName == serverFilter }
        }

        // Filter by search text
        if !searchText.isEmpty {
            result = result.filter { tool in
                tool.name.localizedCaseInsensitiveContains(searchText) ||
                    tool.description.localizedCaseInsensitiveContains(searchText)
            }
        }

        return result
    }

    private var groupedTools: [(server: String, tools: [MCPToolInfo])] {
        let grouped = Dictionary(grouping: filteredTools) { $0.serverName }
        return grouped.map { (server: $0.key, tools: $0.value.sorted { $0.name < $1.name }) }
            .sorted { $0.server < $1.server }
    }

    private func loadAllTools() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response = try await mcpService.getAllTools()
            tools = response.tools
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to load tools: \(String(describing: error))")
        }
    }

    private func loadIntoWorkflowRegistry() async {
        do {
            let response = try await mcpService.loadToolsIntoWorkflowRegistry()
            logger.info("Loaded \(response.toolCount) tools into workflow registry")
            // Could show a success message here
        } catch {
            logger.error("Failed to load tools into workflow registry: \(String(describing: error))")
        }
    }
}

/// Row displaying a single MCP tool
struct MCPToolRow: View {
    let tool: MCPToolInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(tool.name)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.primary)

            if !tool.description.isEmpty {
                Text(tool.description)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    MCPToolsCatalogView()
        .environment(appState.mcpService)
        .frame(width: 900, height: 600)
}
