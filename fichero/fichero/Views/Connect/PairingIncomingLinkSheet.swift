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

    var body: some View {
        NavigationStack {
            Group {
                if isPairing {
                    ProgressView("Connecting…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.largeTitle)
                            .foregroundStyle(.red)
                        Text(errorMessage)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
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
                libraryPath: fields.libraryPath
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
            errorMessage = error.localizedDescription
        }
    }
}

#endif
