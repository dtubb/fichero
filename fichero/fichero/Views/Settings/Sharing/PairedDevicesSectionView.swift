import FicheroAPIClient
import SwiftUI

/// The still-active devices that revoking `id` also revokes: the ones it paired, and theirs (#5351).
func devicesRevokedWith(_ id: String, in devices: [PairedDeviceRecord]) -> [PairedDeviceRecord] {
    var out: [PairedDeviceRecord] = []
    var frontier = [id]
    while let next = frontier.popLast() {
        let kids = devices.filter { candidate in
            !candidate.revoked && candidate.pairedByDeviceId == next && candidate.id != id
                && !out.contains { $0.id == candidate.id }
        }
        out += kids
        frontier += kids.map(\.id)
    }
    return out
}

/// Connected devices, with a named empty state — a device list that simply isn't
/// there when empty teaches the user nothing (#3769 blank-space rule).
struct PairedDevicesSectionView: View {
    let devices: [PairedDeviceRecord]
    let isLoading: Bool
    let canHostRemoteAccess: Bool
    let onRefresh: () -> Void
    let onRevoke: (String) -> Void

    @State private var pendingRevoke: PairedDeviceRecord?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if devices.isEmpty {
                Text("No devices have joined yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(devices) { device in
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(device.name)
                            Text(device.lastSeen, style: .relative)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Remove") {
                            pendingRevoke = device
                        }
                        .buttonStyle(.borderless)
                        .disabled(!canHostRemoteAccess)
                    }
                }
            }
            Button(isLoading ? "Refreshing…" : "Refresh", action: onRefresh)
                .disabled(isLoading || !canHostRemoteAccess)
        }
        .confirmationDialog(
            pendingRevoke.map { "Remove \($0.name)?" } ?? "",
            isPresented: Binding(get: { pendingRevoke != nil }, set: { if !$0 { pendingRevoke = nil } }),
            titleVisibility: .visible,
            presenting: pendingRevoke
        ) { device in
            Button("Remove", role: .destructive) { onRevoke(device.id) }
            Button("Cancel", role: .cancel) {}
        } message: { device in
            let also = devicesRevokedWith(device.id, in: devices)
            Text(also.isEmpty ? "It will no longer be able to connect."
                 : "It will no longer be able to connect. It paired \(also.map(\.name).formatted()), which will be removed too.")
        }
    }
}

#if canImport(AppKit)  // PairingCardView is macOS-only

#Preview("Pairing card: engine not running") {
    PairingCardView(
        pairingCode: nil, qrCodeImage: nil, publicURL: nil, inviteLink: nil,
        isGeneratingPairingCode: false, blocker: .engineNotRunning, errorMessage: nil,
        isResolving: false, onResolve: { _ in }, copiedInvite: false, onCopyInvite: {}
    )
    .padding()
    .frame(width: 420)
}

#Preview("Pairing card: working") {
    PairingCardView(
        pairingCode: nil, qrCodeImage: nil, publicURL: nil, inviteLink: nil,
        isGeneratingPairingCode: true, blocker: nil, errorMessage: nil,
        isResolving: false, onResolve: { _ in }, copiedInvite: false, onCopyInvite: {}
    )
    .padding()
    .frame(width: 420)
}

#endif

#Preview("Connected devices: empty") {
    Form {
        Section("Connected Devices") {
            PairedDevicesSectionView(
                devices: [], isLoading: false, canHostRemoteAccess: true, onRefresh: {}, onRevoke: { _ in }
            )
        }
    }
    .formStyle(.grouped)
    .frame(width: 420)
}
