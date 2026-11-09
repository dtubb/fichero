import SwiftUI

/// The libraries shared with this person, labelled by their host Mac (`sharing.ios.shared-library-chooser`, #5396).
/// The same list the Mac's Shared Libraries section reads; choosing one opens it.
struct SharedLibraryChooserView: View {
    let machines: [PairedMachine]
    let onOpen: (PairedMachine, String) -> Void

    var body: some View {
        List {
            ForEach(SharedMachineSections.sections(machines)) { section in
                Section(section.machine.name) {
                    ForEach(section.rows, id: \.self) { row in
                        switch row {
                        case .library(let path):
                            SharedLibraryRowView(machine: "", library: path) { onOpen(section.machine, path) }
                        case .nothingShared(let sentence):
                            Text(sentence).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if Self.showsHowToPair(machines) { PairedMachinesEmptyView() }
        }
        .navigationTitle("Shared Libraries")
    }

    /// With no library shared yet the list says how to pair, never an empty screen (`sharing.ios.no-empty-detail`).
    static func showsHowToPair(_ machines: [PairedMachine]) -> Bool { SharedMachineSections.showsHowToPair(machines) }
}

#if DEBUG
#Preview("Shared Library Chooser") {
    NavigationStack {
        SharedLibraryChooserView(
            machines: [PairedMachine(id: "https://studio.local:8765", name: "studio.local",
                                     libraries: ["/a/Marshall"])],
            onOpen: { _, _ in })
    }
}
#endif
