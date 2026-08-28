#if os(macOS)
import AppKit
import SwiftUI

/// Fichero ▸ Install Command-Line & MCP Tools… (Daniel, 2026-08-27 — the
/// BBEdit pattern). Installs tiny launcher scripts that exec the SIGNED
/// bundled engine binary with `FICHERO_RUN_MODULE` set: one binary serves
/// the engine, the `fichero` CLI, and the MCP server. Sandbox-honest — the
/// save panel IS the write grant, so no privileged helper is needed.
struct InstallToolsWindow: View {
    @State private var cliStatus: String?
    @State private var mcpStatus: String?
    @State private var mcpInstalledPath = Self.realHomeBin + "/fichero-mcp"

    /// The user's REAL home ± sandbox: NSHomeDirectory() is the container.
    static var realHomeBin: String {
        let home = getpwuid(getuid()).flatMap { String(cString: $0.pointee.pw_dir) }
            ?? NSHomeDirectory()
        return home + "/bin"
    }
    @State private var copied: String?

    var body: some View {
        Form {
            Section {
                Text("The tools run against the Fichero app on this Mac — no separate server to start. Reinstall after moving Fichero.app.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            Section("Command-Line Tool") {
                LabeledContent("fichero") {
                    Button("Install…") { install(name: "fichero", module: "fichero_cli") { cliStatus = $0 } }
                }
                Text("Try `fichero health` or `fichero workflow list` in Terminal. If the command isn't found, add `export PATH=\"$HOME/bin:$PATH\"` to ~/.zshrc.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let cliStatus { statusText(cliStatus) }
            }

            Section("MCP Server") {
                LabeledContent("fichero-mcp") {
                    Button("Install…") {
                        install(name: "fichero-mcp", module: "fichero_mcp.server") { status in
                            mcpStatus = status
                            if let path = status?.split(separator: " ").last.map(String.init),
                               status?.hasPrefix("Installed") == true {
                                mcpInstalledPath = path
                            }
                        }
                    }
                }
                if let mcpStatus { statusText(mcpStatus) }
            }

            Section("Register the MCP server with…") {
                snippetRow(
                    "Claude Code",
                    "claude mcp add fichero -- \(mcpInstalledPath)"
                )
                snippetRow(
                    "Claude Desktop",
                    "\"fichero\": { \"command\": \"\(mcpInstalledPath)\" }",
                    note: "Add inside \"mcpServers\" in ~/Library/Application Support/Claude/claude_desktop_config.json"
                )
                snippetRow(
                    "Codex",
                    "[mcp_servers.fichero]\ncommand = \"\(mcpInstalledPath)\"",
                    note: "Add to ~/.codex/config.toml"
                )
                snippetRow("Anything else", mcpInstalledPath, note: "A stdio MCP server — point any MCP client at this command.")
            }
        }
        .formStyle(.grouped)
        .frame(minWidth: 520, minHeight: 480)
        .navigationTitle("Install Command-Line & MCP Tools")
    }

    private func statusText(_ status: String) -> some View {
        Text(status)
            .font(.caption)
            .foregroundStyle(status.hasPrefix("Installed") ? AnyShapeStyle(.green) : AnyShapeStyle(.red))
    }

    @ViewBuilder
    private func snippetRow(_ title: String, _ snippet: String, note: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.headline)
                Spacer()
                Button(copied == title ? "Copied" : "Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(snippet, forType: .string)
                    copied = title
                }
            }
            Text(snippet)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
            if let note {
                Text(note).font(.caption2).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Installation

    private static var launcherBinary: String {
        Bundle.main.bundlePath
            + "/Contents/Resources/Fichero Server.app/Contents/MacOS/Fichero Server"
    }

    private static func script(module: String) -> String {
        """
        #!/bin/sh
        # Installed by Fichero (\(Bundle.main.bundlePath)).
        # Re-run Fichero ▸ Install Command-Line & MCP Tools… after moving the app.
        export FICHERO_RUN_MODULE=\(module)
        exec "\(launcherBinary)" "$@"

        """
    }

    private func install(name: String, module: String, done: @escaping (String?) -> Void) {
        let panel = NSSavePanel()
        panel.title = "Install \(name)"
        panel.nameFieldStringValue = name
        // ~/bin, not /usr/local/bin: the save panel grants the sandbox
        // exception but not POSIX permission, and /usr/local/bin is
        // root-owned — the write fails after the user already clicked
        // Install (Daniel hit this, 2026-08-27).
        panel.directoryURL = URL(fileURLWithPath: Self.realHomeBin, isDirectory: true)
        panel.canCreateDirectories = true
        panel.showsHiddenFiles = true
        panel.prompt = "Install"
        panel.begin { response in
            guard response == .OK, let url = panel.url else {
                done(nil)
                return
            }
            do {
                try Self.script(module: module).write(to: url, atomically: true, encoding: .utf8)
                try FileManager.default.setAttributes(
                    [.posixPermissions: 0o755], ofItemAtPath: url.path
                )
                done("Installed \(url.path)")
            } catch {
                // The panel granted the write, so a failure here is a real
                // filesystem refusal (e.g. /usr/local/bin not writable).
                done("Failed: \(error.localizedDescription) — try ~/bin or another folder on your PATH.")
            }
        }
    }
}
#endif
