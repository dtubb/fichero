import SwiftUI

/// One library a paired Mac shared with this person, labelled by that Mac; choosing it opens Connect to Library.
struct SharedLibraryRowView: View {
    let machine: String
    let library: String
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 2) {
                Text(URL(fileURLWithPath: library).lastPathComponent).lineLimit(1).truncationMode(.middle)
                if !machine.isEmpty { Text(machine).font(.caption).foregroundStyle(.secondary) }
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
    }
}

/// The group's empty state: how to pair (`sharing.guest.empty-state-says-how-to-pair`).
struct PairedMachinesEmptyView: View {
    #if os(macOS)
    static let sentence = "No Macs yet. On the other Mac, turn on Sharing and copy a pairing link, "
        + "then choose File › Connect to Library…"
    #else
    static let sentence = "No Macs yet. On the Mac, turn on Sharing and show its pairing code, then choose Connect."
    #endif

    var body: some View {
        Text(Self.sentence).font(.caption).foregroundStyle(.secondary)
    }
}

#if DEBUG
#Preview("Shared Library Row") {
    VStack {
        SharedLibraryRowView(machine: "studio.local", library: "/Volumes/Archive/Isthima GHG", onOpen: {})
        PairedMachinesEmptyView()
    }
    .frame(width: 260).padding()
}
#endif
