import SwiftUI

/// Asks once for the host's pairing link when a synced project's host holds no token here (#5898).
/// Connect redeems it with the same machinery as Settings > Sharing; the project stays read-only until it succeeds.
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
            Text(SyncedHostAsk.readOnlyNote).font(.callout).foregroundStyle(.secondary)
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
            // Token and pin only: this project's engine stays where it is, the copy is not switched to the host.
            try PairingService.persistAuthToken(result.deviceToken, for: result.apiRoot)
            onConnected()
        } catch let APIError.httpError(status, message) {
            error = SyncedHostAsk.words(forStatus: status, detail: message)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// The window's one host for the ask: shown for the current project while its copy names a host this Mac holds no
/// token for, until connected or dismissed.
struct SyncedHostAskHost: ViewModifier {
    let libraryRoot: URL?
    @State private var record: SyncedHostRecord?

    func body(content: Content) -> some View {
        content
            .task(id: libraryRoot) { refresh() }
            .sheet(item: Binding(get: { record.map(Ask.init) }, set: { if $0 == nil { later() } })) { ask in
                SyncedHostAskSheet(record: ask.record, onConnected: { record = nil }, onLater: later)
            }
    }

    private struct Ask: Identifiable { let record: SyncedHostRecord; var id: String { record.hostURL } }

    private func refresh() {
        guard let root = libraryRoot, let found = SyncedHostAsk.read(in: root) else { record = nil; return }
        record = SyncedHostAsk.needsAsk(
            found, hasToken: { AuthTokenMiddleware.readRemoteTokenForHost($0) != nil },
            dismissed: SyncedHostAsk.isDismissed(root)) ? found : nil
    }

    private func later() {
        if let root = libraryRoot { SyncedHostAsk.dismiss(root) }
        record = nil
    }
}
