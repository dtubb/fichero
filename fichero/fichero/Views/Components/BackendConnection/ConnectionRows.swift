import Foundation

/// The rows of the toolbar's connection popover: This Mac, then each paired Mac by name
/// (`sharing.connections.popover-lists-every-connection`, Step 8.14, #6434). One row model, no sentences: a state, the
/// library, the address in use, one short time, and for a problem ONE short line with the fix
/// `ConnectionPresentation.Action` names. Pure, so the budget and the states are assertable without a window.
enum ConnectionRows {
    enum State: Equatable {
        case running, starting, stopped  // This Mac's engine
        case connected, asleep, unreachable  // a paired Mac
    }

    struct Row: Identifiable, Equatable {
        let id: String
        let name: String
        let state: State
        let library: String?
        /// "Tailscale" or "LAN"; nil for This Mac.
        let address: String?
        /// ONE short time ("2 min"); nil when the host never answered or for This Mac.
        let lastAnswered: String?
        /// The problem as one short line, never a paragraph.
        let problem: String?
        let fix: ConnectionPresentation.Action?
        let canUse: Bool
        let canDisconnect: Bool
    }

    static let thisMacID = "this-mac"
    static let nameWordBudget = 4
    static let problemWordBudget = 8

    /// What the rows are built from. `states` and `lastAnswered` are keyed by the host's address (`PairedMachine.id`); a host
    /// with no entry has not been asked yet and reads as connected only when one of its libraries is open (`openHosts`).
    /// `inUse` is the host dialled as the whole Mac's engine, if any.
    struct Input {
        var local: State
        var machines: [PairedMachine]
        var openHosts: Set<String> = []
        var states: [String: State] = [:]
        var lastAnswered: [String: Date] = [:]
        var inUse: String?
        var now = Date()
    }

    static func rows(_ input: Input) -> [Row] {
        let (local, machines, inUse, now) = (input.local, input.machines, input.inUse, input.now)
        let thisMac = Row(
            id: thisMacID, name: "This Mac", state: local, library: nil, address: nil, lastAnswered: nil,
            problem: local == .stopped ? "Engine stopped" : nil, fix: local == .stopped ? .restartEngine : nil,
            canUse: inUse != nil, canDisconnect: false)
        let hosts = machines.map { machine -> Row in
            let state = input.states[machine.id] ?? (input.openHosts.contains(machine.id) ? .connected : .asleep)
            let problem = problemLine(state)
            return Row(
                id: machine.id, name: shortName(machine.name), state: state,
                library: machine.libraries.first.map { URL(fileURLWithPath: $0).deletingPathExtension().lastPathComponent },
                address: addressKind(machine.id), lastAnswered: input.lastAnswered[machine.id].map { shortTime(since: $0, now: now) },
                problem: problem, fix: problem == nil ? nil : .reconnect,
                canUse: state == .connected && inUse != machine.id, canDisconnect: true)
        }
        return [thisMac] + hosts
    }

    /// The toolbar badge: how many connections answer.
    static func connectedCount(_ rows: [Row]) -> Int {
        rows.filter { [.running, .connected].contains($0.state) }.count
    }

    static func problemLine(_ state: State) -> String? {
        switch state {
        case .asleep: "Not answering"
        case .unreachable: "Can't reach this Mac"
        default: nil
        }
    }

    /// At most four words.
    static func shortName(_ name: String) -> String {
        name.split(separator: " ").prefix(nameWordBudget).joined(separator: " ")
    }

    static func addressKind(_ apiRoot: String) -> String {
        let host = URL(string: apiRoot)?.host ?? apiRoot
        return host.hasSuffix(".ts.net") || host.hasPrefix("100.") ? "Tailscale" : "LAN"
    }

    /// One short time, no full stop: "now", "2 min", "3 h", "4 d".
    static func shortTime(since date: Date, now: Date) -> String {
        let seconds = max(0, now.timeIntervalSince(date))
        switch seconds {
        case ..<60: return "now"
        case ..<3600: return "\(Int(seconds / 60)) min"
        case ..<86400: return "\(Int(seconds / 3600)) h"
        default: return "\(Int(seconds / 86400)) d"
        }
    }
}
