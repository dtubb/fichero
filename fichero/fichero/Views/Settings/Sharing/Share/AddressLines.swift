import SwiftUI

/// The addresses a link can carry, ONE line each (#6554): a mark for the chosen one, its name and host, where it works or
/// why it cannot (`AddressChoiceModel.line`). Clicking a line that can work chooses it. Shared by Add Device and the project
/// Share sheet (`sharing.share-sheet-offers-both-addresses`), so a greyed Tailscale line and its reason show in both. A
/// sheet with one link per row passes `onCopy` for each line's own Copy; nil hides it.
struct AddressLines: View {
    let rows: [AddressRow]
    let chosen: AddressChoice?
    let onChoose: (AddressChoice) -> Void
    var onCopy: ((AddressChoice) -> Void)?
    /// The one `tailscale serve` command, when the engine names one (`TailnetServeCommandLine`).
    var serveCommand: String?

    /// Whether the lines are worth showing: more than one address, or one that cannot work (it says why).
    static func shows(_ rows: [AddressRow]) -> Bool { rows.count > 1 || rows.contains { !$0.isEnabled } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(rows) { row in
                HStack(spacing: 6) {
                    Button { onChoose(row.choice) } label: {
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
                    if row.isEnabled, let onCopy {
                        Button("Copy") { onCopy(row.choice) }
                            .controlSize(.small)
                            .accessibilityIdentifier("sharing.address.copy.\(row.choice.rawValue)")
                    }
                }
                .accessibilityIdentifier("sharing.address.row.\(row.choice.rawValue)")
            }
            TailnetServeCommandLine(command: serveCommand)
        }
    }
}

#Preview("Address lines") {
    let rows = AddressChoiceModel.rows(sharingAddress: "https://studio.local:8765", tailnetURL: nil, tailnetForward: "none")
    AddressLines(rows: rows, chosen: .thisNetwork, onChoose: { _ in }, onCopy: { _ in })
        .padding()
}
