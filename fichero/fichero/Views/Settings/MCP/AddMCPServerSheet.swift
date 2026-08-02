import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AddMCPServerSheet")

/// Sheet for adding a new MCP server
struct AddMCPServerSheet: View {
    let onAdd: () async -> Void

    @Environment(MCPService.self) var mcpService
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var description = ""
    @State private var transport = "stdio"
    @State private var command = ""
    @State private var args = ""
    @State private var env = ""
    @State private var url = ""
    @State private var headers = ""
    @State private var toolNamePrefix = true
    @State private var enabled = true

    @State private var isSaving = false
    @State private var errorMessage: String?

    private let transportTypes = ["stdio", "http", "sse", "websocket"]

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Add MCP Server")
                    .font(.title2)
                    .fontWeight(.semibold)
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                        .imageScale(.large)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Close")
            }
            .padding()

            Divider()

            // Form
            Form {
                Section("Basic Information") {
                    TextField("Server Name", text: $name)
                        .textFieldStyle(.roundedBorder)

                    TextField("Description (optional)", text: $description)
                        .textFieldStyle(.roundedBorder)

                    Picker("Transport", selection: $transport) {
                        Text("Process (stdio)").tag("stdio")
                        Text("HTTP").tag("http")
                        Text("Server-Sent Events").tag("sse")
                        Text("WebSocket").tag("websocket")
                    }
                    .pickerStyle(.menu)
                }

                // Transport-specific configuration
                if transport == "stdio" {
                    Section("Process Configuration") {
                        TextField("Command (e.g., python)", text: $command)
                            .textFieldStyle(.roundedBorder)

                        TextField("Arguments (space-separated)", text: $args)
                            .textFieldStyle(.roundedBorder)
                            .help("Example: -m mcp_server_time")

                        TextField("Environment (KEY=VALUE, one per line)", text: $env, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .lineLimit(3...6)
                    }
                } else {
                    Section("Network Configuration") {
                        TextField("URL", text: $url)
                            .textFieldStyle(.roundedBorder)
                            .help("Example: http://localhost:8080/mcp")

                        TextField("Headers (KEY: VALUE, one per line)", text: $headers, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .lineLimit(3...6)
                    }
                }

                Section("Options") {
                    Toggle("Prefix tool names with server name", isOn: $toolNamePrefix)
                        .help("e.g., 'time__get_current_time' instead of 'get_current_time'")

                    Toggle("Enable server", isOn: $enabled)
                }

                // Error message
                if let error = errorMessage {
                    Section {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                            Text(error)
                                .foregroundColor(.secondary)
                                .font(.caption)
                        }
                    }
                }
            }
            .formStyle(.grouped)
            .scrollContentBackground(.hidden)
            .padding()

            Divider()

            // Footer buttons
            HStack {
                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)

                Spacer()

                Button("Add Server") {
                    Task { await addServer() }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(name.isEmpty || isSaving || !isValid)
                .buttonStyle(.borderedProminent)
            }
            .padding()
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 600, height: 550)
        #endif
    }

    private var isValid: Bool {
        if name.isEmpty { return false }
        if transport == "stdio" && command.isEmpty { return false }
        if transport != "stdio" && url.isEmpty { return false }
        return true
    }

    private func addServer() async {
        guard isValid else { return }

        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            let request = CreateMCPServerRequest(
                name: name,
                description: description,
                transport: transport,
                command: transport == "stdio" ? command : nil,
                args: parseArgs(args),
                env: parseEnv(env),
                url: transport != "stdio" ? url : nil,
                headers: parseHeaders(headers),
                toolNamePrefix: toolNamePrefix,
                enabled: enabled
            )

            _ = try await mcpService.createServer(request)
            await onAdd()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Failed to add server: \(String(describing: error))")
        }
    }

    private func parseArgs(_ text: String) -> [String] {
        text.split(separator: " ")
            .map { String($0).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    private func parseEnv(_ text: String) -> [String: String] {
        var result: [String: String] = [:]
        for line in text.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }

            if let separatorIndex = trimmed.firstIndex(of: "=") {
                let key = String(trimmed[..<separatorIndex]).trimmingCharacters(in: .whitespaces)
                let remainder = trimmed[trimmed.index(after: separatorIndex)...]
                let value = String(remainder).trimmingCharacters(in: .whitespaces)
                if !key.isEmpty {
                    result[key] = value
                }
            }
        }
        return result
    }

    private func parseHeaders(_ text: String) -> [String: String] {
        var result: [String: String] = [:]
        for line in text.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }

            if let separatorIndex = trimmed.firstIndex(of: ":") {
                let key = String(trimmed[..<separatorIndex]).trimmingCharacters(in: .whitespaces)
                let remainder = trimmed[trimmed.index(after: separatorIndex)...]
                let value = String(remainder).trimmingCharacters(in: .whitespaces)
                if !key.isEmpty {
                    result[key] = value
                }
            }
        }
        return result
    }
}

// MARK: - Preview

#Preview {
    let appState = AppState()

    AddMCPServerSheet(onAdd: {})
        .environment(appState.mcpService)
}
