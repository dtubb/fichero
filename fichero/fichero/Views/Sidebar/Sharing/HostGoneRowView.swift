import SwiftUI

/// The greyed row for a shared project whose host turned Sharing off: the name, one sentence, Forget.
struct HostGoneRowView: View {
    let row: HostGoneRow
    let onForget: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(row.name)
                .lineLimit(1)
                .truncationMode(.middle)
            Text(row.sentence)
                .font(.caption)
        }
        .foregroundStyle(.secondary)
        .contextMenu { Button("Forget", action: onForget) }
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Forget", onForget)
    }
}

#if DEBUG
#Preview("Host Gone Row") {
    HostGoneRowView(row: HostGoneRow(id: UUID(), name: "Marshall", host: "studio.local"), onForget: {})
        .frame(width: 260)
        .padding()
}
#endif
