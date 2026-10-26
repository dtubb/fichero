#if os(iOS) || os(visionOS)
import SwiftUI

/// What a connected iPhone or iPad offers about its connection (#6124): which Mac it is on, Reconnect,
/// Add or Change Server…, Forget This Mac (the sign out: undoes the pairing, back to the Connect screen), Share Log.
struct IOSConnectionMenu: View {
    @Environment(AppState.self) private var appState
    @Environment(\.engineRetry) private var engineRetry

    @State private var choosingServer = false
    @State private var confirmingForget = false
    @State private var logURL: URL?
    @State private var logError: String?

    var body: some View {
        List {
            Section {
                LabeledContent("Connected to", value: EngineConfig.hostString)
                    .accessibilityIdentifier("connection.menu.host")
            }
            Section {
                Button("Reconnect", systemImage: "arrow.clockwise") { Task { await engineRetry?() } }
                    .accessibilityIdentifier("connection.menu.reconnect")
                Button("Add or Change Server…", systemImage: "server.rack") { choosingServer = true }
                    .accessibilityIdentifier("connection.menu.change-server")
                Button("Forget This Mac", systemImage: "xmark.circle", role: .destructive) { confirmingForget = true }
                    .accessibilityIdentifier("connection.menu.forget")
            }
            Section {
                if let logURL {
                    ShareLink(item: logURL) { Label("Share Log", systemImage: "square.and.arrow.up") }
                        .accessibilityIdentifier("connection.menu.share-log")
                } else {
                    Button("Prepare Log to Share", systemImage: "doc.text") { prepareLog() }
                        .accessibilityIdentifier("connection.menu.prepare-log")
                }
                if let logError { Text(logError).font(.footnote).foregroundStyle(.secondary) }
            }
        }
        .navigationTitle("Connection")
        .sheet(isPresented: $choosingServer) {
            ChangeServerSheet { await engineRetry?() }
        }
        .confirmationDialog("Forget this Mac?", isPresented: $confirmingForget, titleVisibility: .visible) {
            Button("Forget This Mac", role: .destructive) {
                Task {
                    // The Mac is told first, with this device's own token; unreachable, the device still forgets it.
                    _ = await RemoteClientPairing.revokeOwnPairing()
                    RemoteClientPairing.forgetPairing()
                    appState.engine.markSetupNeeded()
                }
            }
        } message: {
            Text("This device signs out and returns to Connect, and asks the Mac to remove it from its list of paired "
                + "devices. The projects stay on the Mac. If the Mac cannot be reached now, it keeps listing this "
                + "device until its owner removes it in Sharing.")
        }
    }

    private func prepareLog() {
        do {
            logURL = try LogExport.write()
            logError = nil
        } catch {
            logError = "The log could not be read: \(error.localizedDescription)"
        }
    }
}

#Preview {
    NavigationStack { IOSConnectionMenu() }
        .environment(AppState())
}
#endif
