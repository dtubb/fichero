import FicheroAPIClient
import SwiftUI

/// What the Start / Stop control shows (`activity.mode.start-stop`, #5621,
/// ruled 2026-10-09): at a glance, whether background work is running, held,
/// or paused, why when held, and what a click does. Pure, from the one jobs
/// read (`ActivityStore.backgroundMode`, `.machine`, `.backgroundJobs`). The toolbar control it drew is gone (Run
/// Automatically is a setting, #6441); Project › Activity's Pause / Resume Automatic Work read the mode through it.
struct ActivityModeIndicator: Equatable {
    enum Look: Equatable { case running, held, paused }

    let mode: ActivityMode
    let look: Look
    /// "Running", "Waiting", "Idle", "Paused" (help and accessibility; the toolbar shows the icon).
    let title: String
    let symbol: String
    /// What it means and what a click does, in words.
    let help: String
    /// The mode a click sets: Start while automatic, back to automatic otherwise.
    let primary: ActivityMode

    /// `whyWait` is the engine's reason heavy work is held now (`machine.why_wait`);
    /// it shows as held only while some work is waiting.
    init(mode: ActivityMode, whyWait: String?, hasWaitingWork: Bool, hasRunningWork: Bool = true) {
        self.mode = mode
        let why = whyWait.flatMap { $0.isEmpty ? nil : $0 }.map(Self.withoutPrefix)
        let held = why != nil && hasWaitingWork
        switch mode {
        case .paused:
            look = .paused
            title = "Paused"
            symbol = "pause.circle.fill"
            help = "All background work is paused. Click to run it automatically again."
            primary = .automatic
        case .started:
            look = held ? .held : .running
            title = held ? "Waiting" : (hasRunningWork ? "Running" : "Idle")
            symbol = held ? "hourglass" : (hasRunningWork ? "play.circle.fill" : "play.circle")
            help = (held ? "Waiting because \(why ?? ""), which Run Now cannot override. " : "")
                + "Running now, even while you use the Mac or it is on battery. "
                + "Click to run automatically again."
            primary = .automatic
        case .automatic:
            look = held ? .held : .running
            title = held ? "Waiting" : (hasRunningWork ? "Running" : "Idle")
            symbol = held ? "hourglass" : (hasRunningWork ? "play.circle.fill" : "play.circle")
            help = held
                ? "Waiting because \(why ?? ""). Click to run it now anyway."
                : "Background work runs when the Mac is free. Click to run it now, even while you use the Mac."
            primary = .started
        }
    }

    @MainActor init(store: ActivityStore) {
        self.init(mode: store.backgroundMode, whyWait: store.machine?.whyWait,
                  hasWaitingWork: store.backgroundJobs.contains { $0.state == .waiting },
                  hasRunningWork: store.backgroundJobs.contains { $0.state == .running })
    }

    private static let throttlePrefix = "Waiting: "

    private static func withoutPrefix(_ reason: String) -> String {
        reason.hasPrefix(throttlePrefix) ? String(reason.dropFirst(throttlePrefix.count)) : reason
    }
}
