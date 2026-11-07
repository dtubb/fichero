#if os(iOS) || os(visionOS)
import SwiftUI

// Promoted private → internal: presented by `FicheroSharedPlatformRoot`
// (FicheroApp_iOS.swift) after this type was split out for file_length.
struct PairingIncomingLinkSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(MobileCaptureQueueStore.self) private var captureQueue
    @Environment(\.dismiss) private var dismiss

    let url: URL
    let onConnected: @MainActor () async -> Void

    @State private var isPairing = true
    @State private var errorMessage: String?
    /// A failed pairing, as the one alert (`sharing.alerts.one-alert-per-failure`); the sheet behind it says only that it is not connected.
    @State private var failurePrompt: FailureAlertPrompt?
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            Group {
                if isPairing {
                    ProgressView("Connecting…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if errorMessage != nil {
                    ContentUnavailableView("Not Connected", systemImage: "exclamationmark.triangle")
                }
            }
            .navigationTitle("Connecting…")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .task { await pair() }
        .failureAlert($failurePrompt)
    }

    private func pair() async {
        isPairing = true
        errorMessage = nil
        do {
            let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: url.absoluteString)
            _ = try await RemoteClientPairing.pairAndPersistHost(
                remoteURL: fields.remoteURL,
                pairCode: fields.pairCode,
                deviceName: RemoteClientPairing.defaultDeviceName(),
                expectedSPKIPin: fields.spkiPin,
                libraryPath: fields.libraryPath,
                altURLs: fields.altURLs
            )
            // Pairing persisted the new host; repoint the app-level client so
            // the reconnect probe targets it. Library adoption + reload fire once
            // in the ready transition (`onConnected` → refreshAfterBackendBecameReady,
            // #3113) — no duplicate adopt here.
            appState.reconfigureGeneratedClientsForCurrentHost()
            dismiss()
            await onConnected()
        } catch {
            isPairing = false
            errorMessage = ""
            failurePrompt = SharingFailurePrompt.make(
                pairing: error,
                host: (try? RemoteClientPairing.pairingFields(fromInviteOrPayload: url.absoluteString))
                    .flatMap { URL(string: $0.remoteURL)?.host } ?? "your Mac",
                offers: SharingFailurePrompt.phoneOffers.subtracting([.pasteLinkAgain]),
                perform: { fix in
                    if let page = SharingFailurePrompt.url(for: fix) { openURL(page) } else { Task { await pair() } }
                },
                copy: { PlatformPasteboard.writeString($0) })
        }
    }
}
#Preview {
    PairingIncomingLinkSheet(url: URL(string: "fichero://pair?code=ABC")!, onConnected: {})
        .environment(AppState())
        .environment(LibraryManager.shared)
        .environment(MobileCaptureQueueStore())
}
#endif
