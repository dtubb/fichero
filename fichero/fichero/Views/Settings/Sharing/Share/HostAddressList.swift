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
