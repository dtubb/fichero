import SwiftUI

/// One library a paired Mac shared with this person, labelled by that Mac; choosing it opens Connect to Library.
struct SharedLibraryRowView: View {
    /// The row's symbol: a project's, as on the Mac's project rows, so no sidebar row is drawn bare (#6557).
    nonisolated static let systemImage = LibrarySectionHeader.systemImage

    let machine: String
    let library: String
    /// Set when the host answered and no longer lists this library: the row is greyed with one sentence and does not open.
    var unavailableSentence: String?
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            // Icon and name at the node rows' spacing and icon width (`SidebarNodeLabel`), so the name lines up
            // with the folders' names; the caption lines sit under the name, not the icon.
            HStack(alignment: .firstTextBaseline, spacing: SidebarNodeLabel.spacing) {
                Image(systemName: Self.systemImage)
                    .frame(width: SidebarNodeLabel.iconWidth, alignment: .center)
                VStack(alignment: .leading, spacing: 2) {
                    Text(URL(fileURLWithPath: library).lastPathComponent).lineLimit(1).truncationMode(.middle)
                    if !machine.isEmpty { Text(machine).font(.caption).foregroundStyle(.secondary) }
                    if let unavailableSentence {
                        Text(unavailableSentence).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(unavailableSentence != nil)
        .opacity(unavailableSentence == nil ? 1 : 0.5)
        .accessibilityElement(children: .combine)
    }
}

/// A paired Mac's section heading: the person's name for it, else the host's (#6556). Its context menu renames it; an
/// empty name goes back to the host's own.
struct SharedMachineHeader: View {
    let machine: PairedMachine
    let onRename: (String) -> Void
    @State private var renaming = false
    @State private var draft = ""

    var body: some View {
        Text(machine.shownName)
            .lineLimit(1)
            .truncationMode(.middle)
            .help(machine.name)
            .contextMenu {
                Button("Rename…") {
                    draft = machine.customName ?? ""
                    renaming = true
                }
            }
            .alert("Rename \(machine.shownName)", isPresented: $renaming) {
                TextField(machine.name, text: $draft)
                Button("Rename") { onRename(draft) }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The name this Mac has in your sidebar. Leave it empty to use \(machine.name).")
            }
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
