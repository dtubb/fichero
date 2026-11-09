import SwiftUI

/// The popover's list of every connection (`sharing.connections.popover-lists-every-connection`, #6434): a glyph, a name, the
/// library, an address badge and one short time per row; a problem is one short line with its fix button.
struct ConnectionRowsView: View {
    let rows: [ConnectionRows.Row]
    let onFix: (ConnectionRows.Row) -> Void
    let onDisconnect: (ConnectionRows.Row) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(rows) { row in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Image(systemName: Self.glyph(row.state)).foregroundStyle(Self.tint(row.state))
                            .help(Self.stateName(row.state)).accessibilityLabel(Self.stateName(row.state))
                        Text(row.name).fontWeight(.medium)
                        if let library = row.library { Text(library).foregroundStyle(.secondary).lineLimit(1) }
                        Spacer()
                        if let address = row.address { Text(address).font(.caption).foregroundStyle(.secondary) }
                        if let time = row.lastAnswered { Text(time).font(.caption).foregroundStyle(.secondary) }
                        if row.canDisconnect { Button("Disconnect") { onDisconnect(row) }.buttonStyle(.link) }
                    }
                    if let problem = row.problem, let fix = row.fix {
                        HStack {
                            Text(problem).font(.caption).foregroundStyle(.orange)
                            Button(fix.title) { onFix(row) }.buttonStyle(.link).font(.caption)
                        }
                    }
                }
            }
        }
        .accessibilityIdentifier("backend.connection.rows")
    }

    static func glyph(_ state: ConnectionRows.State) -> String {
        switch state {
        case .running, .connected: "checkmark.circle.fill"
        case .starting: "circle.dotted"
        case .stopped: "stop.circle"
        case .asleep: "moon.zzz"
        case .unreachable: "xmark.circle.fill"
        }
    }

    static func tint(_ state: ConnectionRows.State) -> Color {
        switch state {
        case .running, .connected: .green
        case .starting, .stopped: .secondary
        case .asleep, .unreachable: .orange
        }
    }

    static func stateName(_ state: ConnectionRows.State) -> String {
        switch state {
        case .running: "Running"
        case .starting: "Starting"
        case .stopped: "Stopped"
        case .connected: "Connected"
        case .asleep: "Asleep"
        case .unreachable: "Unreachable"
        }
    }
}

#if DEBUG
#Preview("Connection rows") {
    ConnectionRowsView(
        rows: ConnectionRows.rows(.init(
            local: .running,
            machines: [
                PairedMachine(id: "https://mini.tail1.ts.net:8765", name: "Mac mini", libraries: ["/x/Marshall.fichero"]),
                PairedMachine(id: "https://studio.local:8765", name: "Studio", libraries: ["/x/Jesuits.fichero"])
            ],
            openHosts: ["https://mini.tail1.ts.net:8765"],
            lastAnswered: ["https://mini.tail1.ts.net:8765": Date().addingTimeInterval(-120)])),
        onFix: { _ in }, onDisconnect: { _ in })
        .padding()
        .frame(width: 380)
}
#endif
