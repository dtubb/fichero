import FicheroAPIClient
import SwiftUI

/// What the Start / Stop control shows (`activity.mode.start-stop`, #5621,
/// ruled 2026-10-09): at a glance, whether background work is running, held,
/// or paused, why when held, and what a click does. Pure, from the one jobs
/// read (`ActivityStore.backgroundMode`, `.machine`, `.backgroundJobs`), so the
/// main toolbar's button and the Activity window's cannot disagree.
struct ActivityModeIndicator: Equatable {
    enum Look: Equatable { case running, held, paused }

    let mode: ActivityMode
    let look: Look
    /// "Running", "Held", "Paused".
    let title: String
    let symbol: String
    /// What it means and what a click does, in words.
    let help: String
    /// The mode a click sets: Start while automatic, back to automatic otherwise.
    let primary: ActivityMode

    /// `whyWait` is the engine's reason heavy work is held now (`machine.why_wait`);
    /// it shows as held only while some work is waiting.
    init(mode: ActivityMode, whyWait: String?, hasWaitingWork: Bool) {
        self.mode = mode
        let why = whyWait.flatMap { $0.isEmpty ? nil : $0 }.map(Self.withoutPrefix)
        let held = why != nil && hasWaitingWork
        switch mode {
        case .paused:
            look = .paused
            title = "Paused"
            symbol = "pause.circle.fill"
            help = "Background work is paused. Click to go back to automatic."
            primary = .automatic
        case .started:
            look = held ? .held : .running
            title = held ? "Held" : "Running"
            symbol = held ? "hourglass" : "play.circle.fill"
            help = (held ? "Held: \(why ?? ""), which Start does not override. " : "")
                + "Started: work goes ahead although you're using the Mac or it is on battery. "
                + "Click to go back to automatic."
            primary = .automatic
        case .automatic:
            look = held ? .held : .running
            title = held ? "Held" : "Running"
            symbol = held ? "hourglass" : "play.circle"
            help = held
                ? "Held: \(why ?? ""). Click Start to go ahead anyway."
                : "Background work runs when the Mac is free. Click Start to run it while you use the Mac too."
            primary = .started
        }
    }

    init(store: ActivityStore) {
        self.init(mode: store.backgroundMode, whyWait: store.machine?.whyWait,
                  hasWaitingWork: store.backgroundJobs.contains { $0.state == .waiting })
    }

    private static let throttlePrefix = "Waiting: "

    private static func withoutPrefix(_ reason: String) -> String {
        reason.hasPrefix(throttlePrefix) ? String(reason.dropFirst(throttlePrefix.count)) : reason
    }
}

/// The one Start / Stop control (ruled 2026-10-09): in the main window's
/// toolbar beside the Activity indicator, and in the Activity window's
/// toolbar. A click starts work although the person is at the Mac (or goes
/// back to automatic); the menu also offers Stop, which pauses all work. One
/// engine action behind both places (`ActivityStore.setBackgroundMode`).
struct ActivityModeButton: View {
    let store: ActivityStore
    @State private var failure: String?

    private var indicator: ActivityModeIndicator { ActivityModeIndicator(store: store) }

    var body: some View {
        let indicator = indicator
        Menu {
            Button("Start: Go Ahead While I Use the Mac", systemImage: "play.fill") { set(.started) }
                .disabled(indicator.mode == .started)
            Button("Automatic", systemImage: "wand.and.stars") { set(.automatic) }
                .disabled(indicator.mode == .automatic)
            Button("Stop: Pause All Work", systemImage: "pause.fill") { set(.paused) }
                .disabled(indicator.mode == .paused)
        } label: {
            ActivityModeLabel(indicator: indicator)
        } primaryAction: {
            set(indicator.primary)
        }
        .menuIndicator(.visible)
        .fixedSize()
        .help(indicator.help)
        .accessibilityLabel("Background work: \(indicator.title)")
        .accessibilityHint(indicator.help)
        .accessibilityIdentifier("activity.mode.button")
        .alert("Couldn't Change Background Work", isPresented: Binding(
            get: { failure != nil }, set: { if !$0 { failure = nil } }
        )) {
            Button("OK", role: .cancel) { failure = nil }
        } message: {
            Text(failure ?? "")
        }
    }

    private func set(_ mode: ActivityMode) {
        Task { failure = await store.setBackgroundMode(mode) }
    }
}

/// The control's face: running, held (orange) or paused, at a glance.
struct ActivityModeLabel: View {
    let indicator: ActivityModeIndicator

    var body: some View {
        Label(indicator.title, systemImage: indicator.symbol)
            .labelStyle(.titleAndIcon)
            .foregroundStyle(indicator.look == .held ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
    }
}

#Preview("Start / Stop: running, held, paused") {
    VStack(alignment: .leading, spacing: 12) {
        ActivityModeLabel(indicator: .init(mode: .automatic, whyWait: nil, hasWaitingWork: true))
        ActivityModeLabel(indicator: .init(mode: .automatic, whyWait: "Waiting: you're using the Mac",
                                           hasWaitingWork: true))
        ActivityModeLabel(indicator: .init(mode: .started, whyWait: nil, hasWaitingWork: true))
        ActivityModeLabel(indicator: .init(mode: .paused, whyWait: nil, hasWaitingWork: true))
    }
    .padding()
}
