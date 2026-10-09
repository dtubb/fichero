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
            help = (held ? "Waiting: \(why ?? ""). Run Now cannot override this. " : "")
                + "Running now, even while you use the Mac or it is on battery. "
                + "Click to run automatically again."
            primary = .automatic
        case .automatic:
            look = held ? .held : .running
            title = held ? "Waiting" : (hasRunningWork ? "Running" : "Idle")
            symbol = held ? "hourglass" : (hasRunningWork ? "play.circle.fill" : "play.circle")
            help = held
                ? "Waiting: \(why ?? ""). Click to run now anyway."
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
            // The current mode is ticked, as in a Mac menu (wording, maintainer 2026-10-09).
            Picker("Background Work", selection: Binding(get: { indicator.mode }, set: { set($0) })) {
                Text("Run Now").tag(ActivityMode.started)
                Text("Run Automatically").tag(ActivityMode.automatic)
                Text("Pause All").tag(ActivityMode.paused)
            }
            .pickerStyle(.inline)
            .labelsHidden()
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
            // An icon only, as a toolbar control; the words are in its help (maintainer 2026-10-09).
            .labelStyle(.iconOnly)
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
