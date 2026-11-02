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
    /// Set when the failure is one of the pairing steps: it decides which buttons the sheet offers (`PairingFailureActions`).
    @State private var failure: PairingFailureError?

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
                        failureButtons
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

    private var failureButtons: some View {
        PairingFailureButtons(failure: failure, message: errorMessage ?? "") { Task { await pair() } }
    }

    private func pair() async {
        isPairing = true
        errorMessage = nil
        failure = nil
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
            failure = error as? PairingFailureError
            errorMessage = failure.map { LocalNetworkPolicy.sentence(for: $0.failure, context: $0.context) } ?? error.localizedDescription
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
