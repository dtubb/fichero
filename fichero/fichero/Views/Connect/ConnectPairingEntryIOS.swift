#if os(iOS) || os(tvOS) || os(visionOS)
import SwiftUI
import UIKit

/// Manual fallback/debug pairing entry (#2350): accepts an invite link
/// (`fichero://pair?…`) or raw QR payload text. Reuses the same
/// `RemoteClientPairing.pairingFields(fromInviteOrPayload:)` path the scanner
/// funnels into, so validation (HTTPS/SPKI) is identical — this is entry only,
/// never a bypass. Primary route on visionOS (no camera scanner).
//
// Promoted private → internal: presented by `RemoteConnectionSetupView`
// (IOSPairingViews.swift) after this type was split out of FicheroApp_iOS.swift
// for file_length.
struct ManualPairingEntrySheet: View {
    let isPairing: Bool
    let onCancel: () -> Void
    let onConnect: (String) -> Void

    @State private var invite = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Invite link or QR text", text: $invite, axis: .vertical)
                        .lineLimit(3...6)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                } header: {
                    Text("Paste the invite link or QR text from the host Mac.")
                } footer: {
                    Text("Use this only if the camera is unavailable. The link is validated the same way as a scanned code.")
                }

                Section {
                    #if !os(tvOS)
                    Button {
                        if let pasted = UIPasteboard.general.string {
                            invite = pasted
                        }
                    } label: {
                        Label("Paste from Clipboard", systemImage: "doc.on.clipboard")
                    }
                    .disabled(isPairing)
                    #endif

                    Button {
                        onConnect(invite)
                    } label: {
                        Label(isPairing ? "Connecting…" : "Connect", systemImage: "link")
                    }
                    .disabled(isPairing || invite.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .navigationTitle("Enter Link Manually")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
            }
        }
    }
}

// Promoted private → internal: presented by `RemoteConnectionSetupView`
// (IOSPairingViews.swift) after this type was split out of FicheroApp_iOS.swift
// for file_length.
struct QRCodeScannerSheet: View {
    let onCancel: () -> Void
    let onMessage: (String) -> Void

    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Open Fichero on the Mac, open Settings, and scan the QR code shown there.")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                #if os(tvOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on Apple TV. Use another Fichero device to scan the code.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 320)
                .padding()
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
                #elseif os(visionOS)
                VStack(spacing: 12) {
                    Image(systemName: "qrcode.viewfinder")
                        .font(.largeTitle)
                    Text("Camera QR scanning is unavailable on visionOS. Use another Fichero device to scan the code.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 320)
                .padding()
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
                #else
                QRCodeScannerView(
                    onMessage: onMessage,
                    onFailure: { message in
                        errorMessage = message
                    }
                )
                .frame(minHeight: 320)
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                )
                #endif

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
            }
            .padding()
            .navigationTitle("Scan QR Code")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
            }
        }
    }
}
#endif
