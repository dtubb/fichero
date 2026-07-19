import SwiftUI

extension ShareLibrarySheet {
    /// The link the person you just shared with actually opens.
    ///
    /// It is the SAME `fichero://` payload as the pairing QR and the copyable
    /// pairing link (#3774/#3813): reachable host + SPKI pin + short-lived
    /// single-use pair code. It is NOT the engine's `share_url`, which is a
    /// loopback API URL that 401s and is dead to anyone but this Mac.
    ///
    /// When no reachable address exists (sharing off, loopback only), there is no
    /// working link to make — we say so honestly and point at the switch, rather
    /// than hand out a link that looks valid and isn't. Never a dead control.
    @ViewBuilder
    var shareLinkSection: some View {
        Section("Share Link") {
            if let pairingLink {
                LabeledContent("Link") {
                    Text(pairingLink)
                        .textSelection(.enabled)
                        .font(.caption.monospaced())
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                HStack {
                    Button(copied ? "Copied" : "Copy Link") { copyPairingLink() }
                    if let url = URL(string: pairingLink) {
                        ShareLink(item: url) {
                            Label("Send…", systemImage: "square.and.arrow.up")
                        }
                    }
                }
                Text("This link lets \(sharedPersonName) connect to your library — "
                    + "it carries a single-use code that expires. Share only with them.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if let reason = shareLinkUnavailableReason {
                // Honest fallback only — the common "sharing is off" case is now
                // handled by Share itself (it turns hosting on), so this renders for
                // the genuine cannot-proceed cases (remote engine / iOS) or the brief
                // certificate-minting window. reason.detail explains each honestly; no
                // stale "go to Settings, then reopen" breadcrumb (#3811).
                VStack(alignment: .leading, spacing: 6) {
                    Text(reason.headline)
                        .font(.headline)
                    Text(reason.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                ProgressView("Preparing link…")
            }
        }
    }
}
