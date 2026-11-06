import SwiftUI

/// One paired Mac in the sidebar with the libraries it gave this device; choosing it opens Connect to Library.
struct PairedMachineRowView: View {
    let machine: PairedMachine
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 2) {
                Text(machine.name).lineLimit(1).truncationMode(.middle)
                ForEach(machine.libraries, id: \.self) { path in
                    Text(URL(fileURLWithPath: path).lastPathComponent).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
    }
}

/// The group's empty state: how to pair (`sharing.guest.empty-state-says-how-to-pair`).
struct PairedMachinesEmptyView: View {
    static let sentence = "No Macs yet. On the other Mac, turn on Sharing and copy a pairing link, then choose File › Connect to Library…"

    var body: some View {
        Text(Self.sentence).font(.caption).foregroundStyle(.secondary)
    }
}

#if DEBUG
#Preview("Paired Machine Row") {
    VStack {
        PairedMachineRowView(machine: PairedMachine(id: "https://studio.local:8765", name: "studio.local",
                                                    libraries: ["/Volumes/Archive/Isthima GHG"]), onOpen: {})
        PairedMachinesEmptyView()
    }
    .frame(width: 260).padding()
}
#endif
