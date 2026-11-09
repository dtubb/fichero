import Foundation

/// A Mac this device has paired with, and the libraries it gave this device (`sharing.guest.machines-group`, #6360).
struct PairedMachine: Identifiable, Equatable, Codable {
    /// The host's API address; one row per host.
    let id: String
    let name: String
    var libraries: [String]

    /// The host's name as a person reads it: the address without scheme or port.
    static func displayName(forAPIRoot url: URL) -> String { url.host ?? url.absoluteString }
}

/// Kept on this device so the list is still there after a relaunch. A record that cannot be read is no rows.
enum PairedMachineStore {
    static let key = "fichero.pairedMachines"

    static func load(from defaults: UserDefaults = .standard) -> [PairedMachine] {
        guard let data = defaults.data(forKey: key) else { return [] }
        return (try? JSONDecoder().decode([PairedMachine].self, from: data)) ?? []
    }

    static func save(_ rows: [PairedMachine], to defaults: UserDefaults = .standard) {
        if rows.isEmpty {
            defaults.removeObject(forKey: key)
        } else if let data = try? JSONEncoder().encode(rows) {
            defaults.set(data, forKey: key)
        }
    }

    /// Adds or updates the host's row, keeping the libraries it already gave this device.
    static func record(apiRoot: URL, library: String?, in defaults: UserDefaults = .standard) {
        var rows = load(from: defaults)
        let id = apiRoot.absoluteString
        var libraries = rows.first { $0.id == id }?.libraries ?? []
        if let library, !libraries.contains(library) { libraries.append(library) }
        let row = PairedMachine(id: id, name: PairedMachine.displayName(forAPIRoot: apiRoot), libraries: libraries)
        if let index = rows.firstIndex(where: { $0.id == id }) { rows[index] = row } else { rows.append(row) }
        save(rows, to: defaults)
    }
}

/// What a paired Mac's section lists in the sidebar and the phone's chooser (`sharing.guest.machines-group`, #6459): every
/// paired Mac in the Mac sidebar, so one that shares nothing yet still shows (as "<host> hasn't shared any project yet") instead of vanishing
/// and leaving the how-to-pair sentence to say the Mac was never paired.
enum SharedMachineSections {
    enum Row: Equatable, Hashable {
        case library(String)
        case nothingShared(String)
    }

    struct Section: Identifiable, Equatable {
        let machine: PairedMachine
        let rows: [Row]
        var id: String { machine.id }
    }

    static func sections(_ machines: [PairedMachine]) -> [Section] {
        machines.map { machine in
            Section(machine: machine, rows: machine.libraries.isEmpty
                ? [.nothingShared("\(machine.name) hasn't shared any project yet")] : machine.libraries.map(Row.library))
        }
    }

    /// The how-to-pair sentence is for a device with no paired Mac at all.
    static func showsHowToPair(_ machines: [PairedMachine]) -> Bool { machines.isEmpty }
}
