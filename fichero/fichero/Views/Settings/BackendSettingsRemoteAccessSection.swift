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

    /// The headline. Each cause names ITSELF.
    var headline: String {
        switch self {
        case .engineIsRemote: return "This library is hosted on another machine"
        case .engineNotRunning: return "Fichero's engine isn't running"
        case .sharingNotStarted: return "Sharing hasn't started yet"
        case .addressMissing: return "Fichero needs this Mac's address"
        case .addressInsecure: return "Sharing needs HTTPS"
        case .addressInvalid: return "That address doesn't work"
        case .pinNotDerived: return "Preparing the security certificate"
        }
    }

    var detail: String {
        switch self {
        case .engineIsRemote:
            return "Sharing happens on the Mac that hosts the library. This one is connected to an engine elsewhere."
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
        case .pinNotDerived:
            return "Fichero mints the certificate for this address automatically when sharing "
                + "starts — the QR appears as soon as it's ready. Turning sharing off and on "
                + "again re-mints it if needed."
        }
    }

    /// The button — present ONLY where the app can genuinely perform the cure
    /// itself. nil where it honestly cannot (a remote engine; an address only the
    /// user knows), and then the detail says exactly what to do instead.
    var actionTitle: String? {
        switch self {
        case .engineNotRunning: return "Start Engine"
        case .sharingNotStarted: return "Turn On Sharing"
        // No "Prepare Certificate" button: turning sharing on mints the certificate
        // itself, so this is a transient "preparing" state, never a step the user
        // must trigger (#3811). If minting genuinely fails it stays an honest message
        // and toggling sharing off/on re-runs the mint — not a dead control.
        case .engineIsRemote, .addressMissing, .addressInsecure, .addressInvalid, .pinNotDerived:
            return nil
        }
    }
}

func activePairedDevices(from devices: [PairedDeviceRecord]) -> [PairedDeviceRecord] {
    devices.filter { !$0.revoked }
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
                    "Fichero couldn't draw the QR code. Use the pairing link below — it carries the same invite.",
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
                .background(Color(.textBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .accessibilityLabel("Pairing link, selectable text")
            Text("On the device: Enter Link Manually → paste this.")
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

        Text("This link lets a device connect to your library — share only with people you trust.")
            .font(.caption)
            .foregroundStyle(.secondary)

        // Saves the next person an hour (#3774): the Simulator runs on the Mac's own
        // network stack, so the Mac's loopback engine is reachable from it directly.
        // A real iPhone is a different machine — 127.0.0.1 there means the phone
        // itself, so it must pair to this Mac's address instead.
        Text("iOS Simulator: it shares this Mac's network, so it can reach a local "
             + "engine directly at https://127.0.0.1:8765. A real iPhone or iPad "
             + "cannot — it needs this Mac's address above.")
            .font(.caption2)
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

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Connected Devices")
                    .font(.headline)
                Spacer()
                Button(isLoading ? "Refreshing…" : "Refresh", action: onRefresh)
                    .disabled(isLoading || !canHostRemoteAccess)
                    .buttonStyle(.bordered)
            }

            if devices.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("No devices have joined yet.")
                    Text("Devices that scan the QR code will appear here.")
                }
                .font(.caption)
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
                            onRevoke(device.id)
                        }
                        .buttonStyle(.borderless)
                        .disabled(!canHostRemoteAccess)
                    }
                }
            }
        }
    }
}
#endif
