#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    // MARK: - Advanced (the ONE escape hatch)

    @ViewBuilder
    var advancedSection: some View {
        Section {
            DisclosureGroup("Advanced") {
                // Use an override only for an address the app cannot infer, such as Tailscale or a fixed IP.
                LabeledContent("Automatic address") {
                    Text(Self.autoLocalBaseURL)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .foregroundStyle(.secondary)
                }

                if let tailnet = detectedTailnetURL, tailnet != publicBaseURL {
                    LabeledContent("Tailscale address") {
                        HStack {
                            Text(tailnet)
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                                .foregroundStyle(.secondary)
                            Button("Use") {
                                addressDraft = tailnet
                                publicBaseURL = tailnet
                                Task { await applySharing() }
                            }
                            .disabled(isApplyingChange)
                        }
                    }
                }

                if let command = sharingState?.tailnetServeCommand {
                    // The sandboxed app cannot run the Tailscale CLI: one command to paste (#5317).
                    Text("Fichero can't start the Tailscale connection itself. Paste this in Terminal once:")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack {
                        Text(command)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                        Button("Copy") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(command, forType: .string)
                        }
                    }
                }

                TextField("Address other devices use", text: $addressDraft)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()

                Text("A literal IP address, a .local hostname, or a Tailscale .ts.net hostname. "
                     + "It must be https:// so the connection can be pinned.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Button("Use This Address") {
                        publicBaseURL = addressDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                        Task { await applySharing() }
                    }
                    .disabled(isApplyingChange || addressDraft == publicBaseURL)

                    Button("Restore Automatic") {
                        publicBaseURL = Self.autoLocalBaseURL
                        Task { await applySharing() }
                    }
                    .disabled(isApplyingChange || publicBaseURL == Self.autoLocalBaseURL)
                }

                Divider()

                // The only invite-rotation affordance in the app: mints a fresh
                // one-time code and invalidates the one already on screen.
                Button(isGeneratingCode ? "Resetting Invite…" : "Reset Invite") {
                    Task { await refreshPairingCode() }
                }
                .disabled(isApplyingChange || isGeneratingCode || pairingBlocker != nil)

                Button("Remove All Devices", role: .destructive) {
                    confirmRemoveAllDevices = true
                }
                .disabled(!EngineConfig.engineIsLocal || activePairedDevices(from: pairedDevices).isEmpty)
            }
        }
        .confirmationDialog(
            "Remove all connected devices?",
            isPresented: $confirmRemoveAllDevices,
            titleVisibility: .visible
        ) {
            Button("Remove All Devices", role: .destructive) {
                Task { await revokeAllDevices() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Every device that has joined this project will have to scan a new QR code to get back in.")
        }
    }
}
#endif
