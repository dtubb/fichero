import Foundation

/// A Mac this device has paired with, and the libraries it gave this device (`sharing.guest.machines-group`, #6360).
struct PairedMachine: Identifiable, Equatable, Codable {
    /// The host's API address; one row per host.
    let id: String
    let name: String
    var libraries: [String]
    /// Every address this Mac is known by (#6556): the link's, and the ones the host lists for itself. Two rows that share
    /// one are the same Mac, reached two ways (its `.local` name and its tailnet name).
    var addresses: [String] = []
    /// The name the person gave this Mac (e.g. "Pro"); nil shows the host's own name.
    var customName: String?

    init(id: String, name: String, libraries: [String], addresses: [String] = [], customName: String? = nil) {
        self.id = id
        self.name = name
        self.libraries = libraries
        self.addresses = addresses
        self.customName = customName
    }

    /// Rows saved before #6556 have no addresses or name: they decode with none.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        libraries = try container.decode([String].self, forKey: .libraries)
        addresses = try container.decodeIfPresent([String].self, forKey: .addresses) ?? []
        customName = try container.decodeIfPresent(String.self, forKey: .customName)
    }

    /// The name the sidebar shows: the person's, else the host's.
    var shownName: String {
        let custom = customName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return custom.isEmpty ? name : custom
    }

    /// Every address of this row as a host key (`scheme://host:port`), its own id included.
    var addressKeys: Set<String> { Set(([id] + addresses).compactMap(Self.hostKey)) }

    /// The host's name as a person reads it: the address without scheme or port.
    static func displayName(forAPIRoot url: URL) -> String { url.host ?? url.absoluteString }

    /// An address reduced to what names one listener: scheme, host and port, lowercased; nil for no host.
    static func hostKey(_ address: String) -> String? {
        guard let url = URL(string: address), let host = url.host?.lowercased() else { return nil }
        let scheme = url.scheme?.lowercased() ?? "https"
        return "\(scheme)://\(host):\(url.port.map(String.init) ?? "")"
    }

    /// Folds rows that are the same Mac (#6556): rows sharing any address become one, keeping the first row's id and name,
    /// every library once in order, every address, and the first name the person gave.
    static func merged(_ rows: [PairedMachine]) -> [PairedMachine] {
        var result: [PairedMachine] = []
        for row in rows {
            if let index = result.firstIndex(where: { !$0.addressKeys.isDisjoint(with: row.addressKeys) }) {
                var into = result[index]
                for library in row.libraries where !into.libraries.contains(library) { into.libraries.append(library) }
                for address in [row.id] + row.addresses where !into.addresses.contains(address) && address != into.id {
                    into.addresses.append(address)
                }
                if into.customName == nil { into.customName = row.customName }
                result[index] = into
            } else {
                result.append(row)
            }
        }
        return result
    }
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

    /// Adds or updates the host's row, keeping the libraries it already gave this device. `addresses` are the pairing
    /// link's other addresses for the same Mac, so a later pairing over another of them lands on this row (#6556).
    static func record(apiRoot: URL, library: String?, addresses: [String] = [], in defaults: UserDefaults = .standard) {
        var rows = load(from: defaults)
        let id = apiRoot.absoluteString
        var row = rows.first { $0.id == id }
            ?? PairedMachine(id: id, name: PairedMachine.displayName(forAPIRoot: apiRoot), libraries: [])
        if let library, !row.libraries.contains(library) { row.libraries.append(library) }
        for address in addresses where address != id && !row.addresses.contains(address) { row.addresses.append(address) }
        if let index = rows.firstIndex(where: { $0.id == id }) { rows[index] = row } else { rows.append(row) }
        save(PairedMachine.merged(rows), to: defaults)
    }
}

/// What a paired Mac's section lists in the Mac sidebar (`sharing.guest.machines-group`, #6459): every paired Mac, so one
/// that shares nothing yet still shows (as "<host> hasn't shared any project yet") instead of vanishing and leaving the
/// how-to-pair sentence to say the Mac was never paired. The phone's chooser keeps its own rule.
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

    /// One section per Mac (rows that are the same Mac are folded, #6556), titled by the person's name for it. `openOnHost`
    /// holds, per row id, the libraries the host has open now; a host that answered lists only those, and one that has not
    /// answered keeps every library it gave this device.
    static func sections(_ machines: [PairedMachine], openOnHost: [String: Set<String>] = [:]) -> [Section] {
        PairedMachine.merged(machines).map { machine in
            let open = openOnHost[machine.id].map { paths in Set(paths.map(canonical)) }
            let listed = open.map { open in machine.libraries.filter { open.contains(canonical($0)) } } ?? machine.libraries
            if listed.isEmpty {
                let sentence = machine.libraries.isEmpty || open == nil
                    ? "\(machine.shownName) hasn't shared any project yet"
                    : "\(machine.shownName) has none of its shared projects open"
                return Section(machine: machine, rows: [.nothingShared(sentence)])
            }
            return Section(machine: machine, rows: listed.map(Row.library))
        }
    }

    private static func canonical(_ path: String) -> String { URL(fileURLWithPath: path).standardized.path }
}

extension LibraryManager {
    /// Gives a paired Mac the person's own name (#6556); an empty name goes back to the host's.
    func renamePairedMachine(_ id: String, to name: String) {
        guard let index = pairedMachines.firstIndex(where: { $0.id == id }) else { return }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        pairedMachines[index].customName = trimmed.isEmpty ? nil : trimmed
        PairedMachineStore.save(pairedMachines)
    }
}
