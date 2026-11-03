import SwiftUI

/// The engine's own address list under the sheet's choices, in its order, a dead address saying why
/// (`sharing.address-choice`: the list the link carries, not a copy the app works out).
struct HostAddressList: View {
    let records: [HostAddressRecord]

    var body: some View {
        if !records.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(HostAddressRecord.lines(records).enumerated()), id: \.offset) { _, line in
                    Text(line).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
            .accessibilityIdentifier("sharing.address.engine-list")
        }
    }
}

#Preview("Host address list") {
    HostAddressList(records: [
        HostAddressRecord(url: "https://studio.local:8765", listening: true, label: nil, reason: nil),
        HostAddressRecord(url: "https://studio.tail1234.ts.net:8765", listening: true, label: "Tailscale", reason: nil),
        HostAddressRecord(url: "https://192.168.1.20:8765", listening: false, label: "Wi-Fi", reason: "it changed; turn Sharing off and on")
    ])
    .padding()
}
