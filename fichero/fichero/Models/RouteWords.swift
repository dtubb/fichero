import FicheroAPIClient
import Foundation

/// The routes for the volume in words (`source.onboard.routes-for-the-volume`, #4951): each figure says where it came from, measured,
/// estimate or unknown, in the engine's own marking; a figure with no value says it is unknown and never a made-up one. Pure.
struct RouteWords: Identifiable, Equatable {
    let id: String
    let title: String
    let cost: String
    let time: String
    let accuracy: String
    let leavesThisMac: Bool

    nonisolated init(_ route: Components.Schemas.Route) {
        id = route.id
        title = route.title
        cost = Self.figure(route.costUsd, label: "Cost") { $0.formatted(.currency(code: "USD")) }
        time = Self.figure(route.timeSeconds, label: "Time") { seconds in
            Duration.seconds(seconds).formatted(.units(allowed: [.days, .hours, .minutes], width: .abbreviated, maximumUnitCount: 2))
        }
        accuracy = Self.figure(route.accuracyCer, label: "Error rate") { $0.formatted(.percent.precision(.fractionLength(1))) }
        leavesThisMac = route.leavesThisMac
    }

    /// "Cost $12.40 · estimate", or "Time unknown": a figure with a value names its basis; one without says so.
    nonisolated static func figure(_ figure: Components.Schemas.Figure?, label: String, format: (Double) -> String) -> String {
        guard let figure, let value = figure.value, figure.basis != "unknown" else { return "\(label) unknown" }
        return "\(label) \(format(value)) · \(figure.basis)"
    }
}
