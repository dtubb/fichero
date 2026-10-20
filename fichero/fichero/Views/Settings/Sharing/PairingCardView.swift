#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

// The pairing card, its blocker vocabulary, and the connected-devices list.
//
// This file used to ALSO hold `BackendSettingsRemoteAccessSection` — a second,
// parallel host-side pairing UI ("Share This Mac") living under Engine → Backend,
// with its own toggle, its own hand-typed URL, its own editable SPKI pin field and
// its own device list, all sharing the same @AppStorage keys as Library Access →
// Devices. Two surfaces that disagree is why pairing felt incoherent and why "the
// QR vanished" (#3769) had two different sets of causes (#3777).
//
// There is now ONE host-side pairing surface: `ShareSettingsView`
// (Settings → Library Access → Devices). What survives here are the pieces that
// surface worth keeping — the honest blocker vocabulary and the copyable pairing
// link (#3774/#3776) — which `ShareSettingsView` now renders.
//
// ponytail: the file keeps its old name so its Xcode target membership is
// untouched; renaming it to PairingCard.swift is a project-file change, not a
// code change.

/// Why the pairing card cannot show a QR, as a value rather than a lone string
/// (#3776/#3769). Each case carries its OWN headline — the card no longer prints
/// "Secure sharing needs HTTPS" over a stopped engine — and its own cure, so a
/// blocker is never a dead end. Non-negotiable: never a blank space, never a
/// dead control; if we cannot proceed, say why and offer the fix.
enum PairingBlocker: Equatable {
    /// The library is served by an engine on ANOTHER machine, so this Mac has
    /// nothing to share. Nothing the app can do here — that is honest, not a dead end.
    case engineIsRemote
    /// The engine on this Mac is not running. The app can start it.
    case engineNotRunning
    /// Sharing has not been started yet. The app can start it — the user does not
    /// "enable a subsystem" first, they just share.
    case sharingNotStarted
    /// No reachable address for this Mac yet. Sharing derives one automatically
    /// (`https://<hostname>.local:<port>`), so this should be unreachable in
    /// practice — it only appears if someone cleared the address under Advanced.
    case addressMissing
    case addressInsecure
    case addressInvalid(String)
    /// The SPKI pin could not be derived. This is the trap: the pin is computed,
    /// not typed, and the derivation is optional — a nil used to blank the card.
    /// Restarting the engine mints the TLS material and derives it.
    case pinNotDerived
    /// The same, on an engine this app did not start (Dev Local): restarting sharing cannot mint a pin there (#5891).
    case pinNotDerivedOnExternalEngine

    /// The headline. Each cause names ITSELF.
    var headline: String {
        switch self {
        case .engineIsRemote: return "This project is hosted on another machine"
        case .engineNotRunning: return "Fichero's engine isn't running"
        case .sharingNotStarted: return "Sharing hasn't started yet"
        case .addressMissing: return "Fichero needs this Mac's address"
        case .addressInsecure: return "Sharing needs HTTPS"
        case .addressInvalid: return "That address doesn't work"
        case .pinNotDerived: return "Preparing the security certificate"
        case .pinNotDerivedOnExternalEngine: return "No security certificate for this address"
        }
    }

    var detail: String {
        switch self {
        case .engineIsRemote:
            return "Sharing happens on the Mac that hosts the project. This one is connected to an engine elsewhere."
        case .engineNotRunning:
            return "The QR code needs a running engine to pair against."
        case .sharingNotStarted:
            return "Turn sharing on and Fichero will prepare the address, the certificate and the invite for you."
        case .addressMissing:
            return "Fichero normally works this out itself. Restore the automatic address under Advanced."
        case .addressInsecure:
            return "Devices pair over HTTPS so the connection can be pinned. Restore the automatic address under Advanced."
        case .addressInvalid(let reason):
            return reason
        case .pinNotDerivedOnExternalEngine:
            return "This engine was started outside Fichero, so Fichero can't make its certificate pin; "
                + "restarting sharing here would change nothing. Start the engine from Fichero, or give it the pin."
        case .pinNotDerived:
            return "Fichero has no certificate pin filed for this address yet. Making the link restarts "
                + "sharing, which mints it; any work running in the engine is stopped, so do it when nothing is running."
        }
    }

    /// The button — present ONLY where the app can genuinely perform the cure
    /// itself. nil where it honestly cannot (a remote engine; an address only the
    /// user knows), and then the detail says exactly what to do instead.
    var actionTitle: String? {
        switch self {
        case .engineNotRunning: return "Start Server"
        case .sharingNotStarted: return "Turn On Sharing"
        // The pin is normally minted when sharing turns on; when it is missing anyway the cure restarts the
        // engine, which stops work in flight, so it is a button the person presses, never automatic (#5891).
        case .pinNotDerived: return "Make a Pairing Link"
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid, .pinNotDerivedOnExternalEngine:
            return nil
        }
    }
}

/// Copy Pairing Link, as a value (#5891, `sharing.pairing.copy-link-says-why`): the link is copied and the clipboard is
/// read back, or the person is told in words why not. It used to do nothing, silently, when there was no link (no
/// pin derived for this address yet) and the card printed "use the pairing link below" over nothing.
enum PairingLinkCopy {
    enum Outcome: Equatable {
        case copied
        /// Nothing was copied; the sentence says why.
        case notCopied(String)
    }

    /// Why there is no link, in words: the blocker's own headline and cure when the card has one, else the general case.
    static func noLinkReason(blocker: PairingBlocker?) -> String {
        if let blocker { return "\(blocker.headline). \(blocker.detail)" }
        return "The pairing link isn't ready: this Mac has no address and certificate pin to put in it yet. "
            + "Turning sharing off and on prepares them."
    }

    static func attempt(link: String?, blocker: PairingBlocker?, write: (String) -> Void,
                        read: () -> String?) -> Outcome {
        guard let link else { return .notCopied(noLinkReason(blocker: blocker)) }
        write(link)
        guard read() == link else {
            return .notCopied("Fichero couldn't copy the link to the clipboard. Select the pairing link above and copy it by hand.")
        }
        return .copied
    }
}

func activePairedDevices(from devices: [PairedDeviceRecord]) -> [PairedDeviceRecord] {
    devices.filter { !$0.revoked }
}

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

/// The one pairing card. Four states, none of them blank: READY (QR + link),
/// PREPARING (progress), BLOCKED (named cause + its cure), and — only ever
/// alongside one of those — an error line.
struct PairingCardView: View {
    let pairingCode: PairingCodeRecord?
    let qrCodeImage: PlatformImage?
    let publicURL: String?
    let inviteLink: String?
    let isGeneratingPairingCode: Bool
    let blocker: PairingBlocker?
    let errorMessage: String?
    let isResolving: Bool
    let onResolve: (PairingBlocker) -> Void
    let copiedInvite: Bool
    let onCopyInvite: () -> Void
    /// What the last Copy said when it copied nothing, in words (#5891).
    var copyNote: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let pairingCode {
                readyCard(pairingCode)
            } else if isGeneratingPairingCode {
                ProgressView("Preparing QR code…")
            } else if let blocker {
                blockedCard(blocker)
            } else if let errorMessage {
                // Belt and braces: an error with no blocker and no code still says
                // something. The card is never empty.
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func readyCard(_ pairingCode: PairingCodeRecord) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let image = qrCodeImage {
                HStack {
                    Spacer(minLength: 0)
                    Image(platformImage: image)
                        .interpolation(.none)
                        .resizable()
                        .frame(width: 220, height: 220)
                        .accessibilityLabel("Pairing QR code")
                    Spacer(minLength: 0)
                }
                Text("Scan this with Fichero on another device to connect.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                // The QR encoder can fail even when everything else is ready. Say so
                // rather than printing "Scan this" beside nothing (#3769).
                Label(
                    inviteLink == nil
                        ? "Fichero couldn't draw the QR code, and there is no pairing link yet."
                        : "Fichero couldn't draw the QR code. Use the pairing link below — it carries the same invite.",
                    systemImage: "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(.orange)
            }

            if let publicURL {
                LabeledContent("Address") {
                    Text(publicURL)
                        .textSelection(.enabled)
                }
                .font(.caption)
            }

            if let inviteLink {
                inviteLinkBlock(inviteLink)
            } else {
                // Never a card with a code and neither a link nor a reason (#5891).
                VStack(alignment: .leading, spacing: 4) {
                    Label(PairingLinkCopy.noLinkReason(blocker: blocker), systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    if let actionTitle = blocker?.actionTitle, let blocker {
                        Button(isResolving ? "Working…" : actionTitle) { onResolve(blocker) }
                            .buttonStyle(.bordered)
                            .disabled(isResolving)
                    }
                }
            }
            if let copyNote {
                Label(copyNote, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .accessibilityIdentifier("sharing.pairing.copyNote")
            }

            Text("Expires \(pairingCode.expiresAt.formatted(date: .omitted, time: .shortened))")
                .font(.caption)
                .foregroundStyle(.secondary)

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }

    /// The pairing link, as SELECTABLE TEXT (#3774). A QR is useless in the iOS
    /// Simulator — it has no camera — so manual entry is not a fallback there, it is
    /// the only way to pair. This is the exact same payload the QR encodes, produced
    /// by the same `RemoteClientPairing.inviteLinkString(from:)` the device's "Enter
    /// Link Manually" already parses: same SPKI pin, same one-time code, same expiry.
    /// Showing it changes convenience, not trust.
    @ViewBuilder
    private func inviteLinkBlock(_ inviteLink: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Pairing link")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(inviteLink)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .lineLimit(3)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(6)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 4))
                .accessibilityLabel("Pairing link, selectable text")
            Text("On the other device, choose Enter Link Manually and paste this.")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(ShareLibrarySheet.syncedCopyHint)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }

        HStack {
            Button(copiedInvite ? "Pairing Link Copied" : "Copy Pairing Link", action: onCopyInvite)
            if let shareURL = URL(string: inviteLink) {
                ShareLink(item: shareURL) {
                    Label("Share Link", systemImage: "square.and.arrow.up")
                }
            }
        }
        .buttonStyle(.bordered)

        Text("This link lets a device connect to your project — share only with people you trust.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    @ViewBuilder
    private func blockedCard(_ blocker: PairingBlocker) -> some View {
        // Each cause states ITSELF and offers its cure. The old code printed
        // "Secure sharing needs HTTPS" over every blocker — so a stopped engine was
        // reported as an HTTPS problem, which is simply false.
        VStack(alignment: .leading, spacing: 6) {
            Text(blocker.headline)
                .font(.headline)
            Text(blocker.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let actionTitle = blocker.actionTitle {
                Button(isResolving ? "Working…" : actionTitle) {
                    onResolve(blocker)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isResolving)
            }
            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
    }
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
#endif
