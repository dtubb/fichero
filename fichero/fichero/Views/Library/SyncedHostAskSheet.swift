import SwiftUI

/// Asks once for the host's pairing link when a synced project's host holds no token here (#5898).
/// Connect redeems it with the same machinery as Settings > Sharing.
struct SyncedHostAskSheet: View {
    let record: SyncedHostRecord
    let onConnected: () -> Void
    let onLater: () -> Void
    @State private var link = ""
    @State private var error: String?
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(SyncedHostAsk.sentence(record))
            TextField("Pairing link", text: $link).textFieldStyle(.roundedBorder)
            if let error { Text(error).font(.callout).foregroundStyle(.red) }
            HStack {
                Spacer()
                Button("Not Now", action: onLater).keyboardShortcut(.cancelAction)
                Button("Connect") { Task { await connect() } }
                    .keyboardShortcut(.defaultAction)
                    .disabled(working || link.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding()
        .frame(width: 420)
    }

    private func connect() async {
        working = true
        defer { working = false }
        do {
            let fields = try SyncedHostAsk.fields(fromLink: link, record: record)
            let result = try await RemoteClientPairing.pairDevice(
                remoteURL: fields.remoteURL, pairCode: fields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(), expectedSPKIPin: fields.spkiPin)
            try await RemoteClientPairing.probeRemoteHealth(at: result.apiRoot, expectedSPKIPin: fields.spkiPin)
            // Token, pin and expiry only: this Mac's engine stays where it is, the copy is not switched to the host.
            try RemoteClientPairing.persistHostCredentials(result, expectedSPKIPin: fields.spkiPin)
            onConnected()
        } catch let APIError.httpError(status, message) {
            error = SyncedHostAsk.words(forStatus: status, detail: message)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

#Preview("Asks once for the host's pairing link") {
    SyncedHostAskSheet(
        record: SyncedHostRecord(hostURL: "https://studio.example.ts.net", hostName: "Studio Mac", person: "Ana"),
        onConnected: {}, onLater: {})
}

/// The window's one host for the ask: shown for the current project while the engine reports a host its copy names
/// and this Mac holds no token for it, until connected or dismissed.
struct SyncedHostAskHost: ViewModifier {
    let libraryPath: String?
    @State private var record: SyncedHostRecord?
    private let registry = KnownLibraryRegistryStore.shared

    func body(content: Content) -> some View {
        content
            .task(id: Key(path: libraryPath, hosts: registry.syncedHosts)) { refresh() }
            .sheet(item: Binding(get: { record.map(Ask.init) }, set: { if $0 == nil { later() } })) { ask in
                SyncedHostAskSheet(record: ask.record, onConnected: { record = nil }, onLater: later)
            }
    }

    private struct Key: Equatable { let path: String?; let hosts: [String: SyncedHostRecord] }
    private struct Ask: Identifiable { let record: SyncedHostRecord; var id: String { record.hostURL } }

    private func refresh() {
        guard let path = libraryPath, let found = registry.syncedHosts[path] else { record = nil; return }
        record = SyncedHostAsk.needsAsk(
            found, hasToken: { AuthTokenMiddleware.readRemoteTokenForHost($0) != nil },
            dismissed: SyncedHostAsk.isDismissed(path)) ? found : nil
    }

    private func later() {
        if let path = libraryPath { SyncedHostAsk.dismiss(path) }
        record = nil
    }
}
