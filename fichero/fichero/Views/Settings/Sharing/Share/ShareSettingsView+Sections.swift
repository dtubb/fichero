#if canImport(AppKit)
import CoreImage
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - Sections and sheets

    /// The Devices list: name and when last seen, `+ Add Device…` and `−` (multi-select Remove). Blank when empty, no Refresh.
    @ViewBuilder
    var devicesSection: some View {
        let devices = activePairedDevices(from: pairedDevices)
        Section("Devices") {
            List(devices, selection: $selectedDevices) { device in
                HStack {
                    Text(device.name)
                    Spacer()
                    Text(device.lastSeen, style: .relative)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .tag(device.id)
            }
            .frame(minHeight: devices.isEmpty ? 0 : 80)
            HStack {
                Button(SharingPaneText.addDevice) { showAddDevice = true }
                Button("−") { confirmRemoveSelected = true }
                    .help("Remove the selected devices")
                    .disabled(!SharingPaneText.canRemove(selected: selectedDevices.count, engineIsLocal: EngineConfig.engineIsLocal))
            }
        }
        .confirmationDialog(
            SharingPaneText.removeQuestion(
                count: selectedDevices.count, firstName: devices.first { selectedDevices.contains($0.id) }?.name),
            isPresented: $confirmRemoveSelected,
            titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) { Task { await revokeSelected() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            let also = selectedDevices.flatMap { devicesRevokedWith($0, in: pairedDevices) }
                .filter { !selectedDevices.contains($0.id) }
            Text(also.isEmpty ? "They will no longer be able to connect."
                 : """
                   They will no longer be able to connect. They paired \(Set(also.map(\.name)).sorted().formatted()), \
                   which will be removed too.
                   """)
        }
    }

    /// Add Device: asks for nothing: the QR, the code, when it expires, Copy Link and Done (`sharing.settings.add-device-sheet`).
    @ViewBuilder
    var addDeviceSheet: some View {
        let phase = AddDeviceSheetModel.phase(
            blocker: pairingBlocker, hasCode: pairingCode != nil, hasLink: inviteLinkString != nil,
            isWorking: isApplyingChange || isGeneratingCode)
        VStack(spacing: 12) {
            switch phase {
            case .finishing:
                ProgressView("Finishing setup…")
            case .ready, .notReady:
                addressRowsView
                if let image = qrImage {
                    Image(platformImage: image)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 220, height: 220)
                        .accessibilityLabel("Pairing QR code")
                }
                if let code = pairingCode {
                    Text(AddDeviceSheetModel.codeText(code.code))
                        .font(.title2.monospacedDigit())
                    Text(AddDeviceSheetModel.expiresText(expiresAt: code.expiresAt))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if phase == .notReady {
                    Text("Not ready yet").font(.caption).foregroundStyle(.secondary)
                }
            case .finishSetup:
                Button("Finish Setup") { if let blocker = pairingBlocker { Task { await resolve(blocker) } } }
                    .buttonStyle(.borderedProminent)
            case .start:
                Button("Start") { if let blocker = pairingBlocker { Task { await resolve(blocker) } } }
                    .buttonStyle(.borderedProminent)
            case .failed(let line):
                Text(line).foregroundStyle(.secondary)
            }
            if let note = copyNote {
                Text(note).font(.caption).foregroundStyle(.red)
            }
            HStack {
                Button(copiedInvite ? "Link Copied" : "Copy Link", action: copyInvite)
                    .disabled(phase != .ready)
                Spacer()
                Button("Done") { showAddDevice = false; Task { await refreshDevices() } }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(minWidth: 320)
        .onChange(of: inviteLinkString) { _, _ in copyNote = nil }
    }

    /// The addresses this Mac can be reached at, ONE line each (#6554): name, host, where it works or why it cannot, and its
    /// own Copy (`sharing.share-sheet-offers-both-addresses`, #5318). Clicking a line that can work makes it the one the QR
    /// and Copy Link carry, ticked; nothing else on the sheet repeats an address.
    @ViewBuilder
    var addressRowsView: some View {
        let rows = addressRows
        if rows.count > 1 || rows.contains(where: { !$0.isEnabled }) {
            let chosen = AddressChoiceModel.shownChoice(addressChoice, rows: rows)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(rows) { row in
                    HStack(spacing: 6) {
                        Button { addressChoice = row.choice } label: {
                            HStack(spacing: 6) {
                                Image(systemName: row.choice == chosen ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(row.isEnabled ? Color.accentColor : Color.secondary)
                                    .accessibilityHidden(true)
                                Text(AddressChoiceModel.line(row))
                                    .font(.caption).foregroundStyle(row.isEnabled ? .primary : .secondary)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.leading)
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(!row.isEnabled)
                        .accessibilityAddTraits(row.choice == chosen ? .isSelected : [])
                        Spacer()
                        if row.isEnabled {
                            Button("Copy") { copyInvite(for: row.choice) }
                                .controlSize(.small)
                                .accessibilityIdentifier("sharing.address.copy.\(row.choice.rawValue)")
                        }
                    }
                    .accessibilityIdentifier("sharing.address.row.\(row.choice.rawValue)")
                }
                TailnetServeCommandLine(command: sharingState?.tailnetServeCommand)
                if AddressChoiceModel.showsCampusNote(rows: rows) {
                    Text(AddressChoiceModel.campusNote).font(.caption).foregroundStyle(.secondary)
                        .accessibilityIdentifier("sharing.address.campus-note")
                }
            }
        }
    }

    /// Connect to Another Mac: hosts the existing client pairing section on a sheet (`sharing.settings.connect-sheet`).
    var connectSheet: some View {
        VStack(spacing: 12) {
            Form {
                MacRemoteClientPairingSection(
                    appState: appState, backendService: backendService, libraryManager: libraryManager,
                    onConnected: { showConnect = false })
            }
            .formStyle(.grouped)
            HStack {
                Spacer()
                Button("Cancel") { showConnect = false }.keyboardShortcut(.cancelAction)
            }
        }
        .padding()
        .frame(minWidth: 460, minHeight: 360)
    }
}
#endif
