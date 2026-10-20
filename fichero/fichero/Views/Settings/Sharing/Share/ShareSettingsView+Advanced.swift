#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    // MARK: - Advanced (the ONE escape hatch)

    /// Commit the Address field on Return: a blank or invalid draft is not committed (the red line says why).
    func commitAddress() {
        let text = addressDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard SharingPaneText.addressProblem(addressDraft) == nil, text != publicBaseURL else { return }
        publicBaseURL = text.isEmpty ? Self.autoLocalBaseURL : text
        Task { await applySharing() }
    }

    @ViewBuilder
    var advancedSection: some View {
        Section {
            DisclosureGroup("Advanced") {
                // An address the app cannot infer, such as a fixed IP or a Tailscale name: committed on Return.
                HStack {
                    TextField("Address", text: $addressDraft)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                        .onSubmit(commitAddress)
                    Button("Reset") {
                        addressDraft = Self.autoLocalBaseURL
                        publicBaseURL = Self.autoLocalBaseURL
                        Task { await applySharing() }
                    }
                    .disabled(isApplyingChange || publicBaseURL == Self.autoLocalBaseURL)
                }
                if let problem = SharingPaneText.addressProblem(addressDraft) {
                    Text(problem)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                if let tailnet = detectedTailnetURL, tailnet != publicBaseURL {
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

                if let command = sharingState?.tailnetServeCommand {
                    // The sandboxed app cannot run the Tailscale CLI: one command to paste (#5317).
                    Text("Run once in Terminal:")
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

                // The only invite-rotation affordance in the app: mints a fresh
                // one-time code and invalidates the one already on screen.
                Button(isGeneratingCode ? "Resetting Invite…" : "Reset Invite") {
                    Task { await refreshPairingCode() }
                }
                .disabled(isApplyingChange || isGeneratingCode || pairingBlocker != nil)

                // Multi-user lives here, not on the main pane (`sharing.settings.multiuser-out-of-sharing`).
                Toggle(isOn: multiuserBinding) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(SharingToggles.label(.multiUser))
                        Text(SharingToggles.caption(.multiUser))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .disabled(isApplyingChange || !EngineConfig.engineIsLocal)
            }
        }
    }
}
#endif
