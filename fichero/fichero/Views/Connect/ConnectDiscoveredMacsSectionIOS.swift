#if os(iOS) || os(tvOS) || os(visionOS)
import SwiftUI

/// Discovered-Mac list that leads first-run onboarding (#3102). Discovery only
/// surfaces *which* Mac is on the LAN; selecting one opens the QR scanner because
/// pairing needs the code + SPKI pin shown on that Mac — the scan grants trust.
/// Reads BonjourDiscoveryService (Services/Connectivity); iOS-only view.
struct DiscoveredMacsSection: View {
    @ObservedObject var discovery: BonjourDiscoveryService
    let isPairing: Bool
    let onSelectHost: () -> Void

    var body: some View {
        Section {
            if discovery.hosts.isEmpty {
                HStack(spacing: 10) {
                    ProgressView().controlSize(.small)
                    Text("Searching for Fichero on your network…")
                        .foregroundStyle(.secondary)
                }
            } else {
                ForEach(discovery.hosts) { host in
                    Button(action: onSelectHost) {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(host.displayName)
                                Text(subtitle(for: host))
                                    .font(.caption)
                                    .foregroundStyle(host.didFailResolve ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
                            }
                        } icon: {
                            Image(systemName: host.didFailResolve ? "exclamationmark.triangle" : "desktopcomputer")
                                .foregroundStyle(host.didFailResolve ? Color.orange : Color.accentColor)
                        }
                    }
                    .disabled(isPairing)
                }
            }
        } header: {
            Text("Connect to your Mac")
        }
    }

    /// Distinguish the three discovery states so a candidate never lies about
    /// being reachable (#3371): resolved, resolve-failed (visible), or still
    /// resolving.
    private func subtitle(for host: BonjourHostRecord) -> String {
        if host.hasReachableURL {
            return "On your network — scan its QR code to pair"
        }
        if host.didFailResolve {
            return "Couldn't reach it — make sure it's on and sharing, then try again"
        }
        return "Found — scan its QR code to pair"
    }
}
#endif
