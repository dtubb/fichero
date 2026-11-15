import FicheroAPIClient
import SwiftUI

/// The three global controls (`activity.window.run-controls`, decision 30, #6588).
enum ActivityRunControl: Sendable {
    case pauseAll, continueAll, stopAll
}

/// Xcode's run controls for all work, at the far left of the Activity window's toolbar and of every main window's: ONE
/// Play/Pause button that turns into the other, and Stop. They act on every open project, through each project's engine
/// action (`activity.pause_all` / `continue_all` / `stop_all`); the engine's summary says which the button shows.
struct ActivityRunControlsButtons: View {
    @Environment(LibraryManager.self) private var libraryManager
    @State private var confirmingStop = false
    @State private var notice: String?

    /// What the one button shows, from every project's summary.
    enum Shows: Equatable { case pause, play, none }

    /// Play while any project holds work Pause All paused; else Pause while anything runs or waits; else nothing to do.
    nonisolated static func shows(_ summaries: [Components.Schemas.ActivitySummary?]) -> Shows {
        let controls = summaries.compactMap { $0?.controls }
        if controls.contains(.play) { return .play }
        if controls.contains(.pause) { return .pause }
        return .none
    }

    /// How many pieces of work Stop All stops, summed over the projects.
    nonisolated static func stoppable(_ summaries: [Components.Schemas.ActivitySummary?]) -> Int {
        summaries.reduce(0) { $0 + ($1?.stoppable ?? 0) }
    }

    /// The question Stop All asks, once.
    nonisolated static func stopQuestion(_ count: Int) -> String {
        "Stop \(count) \(count == 1 ? "piece" : "pieces") of work?"
    }

    private var stores: [ActivityStore] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary, !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references.map(\.activityStore)
    }

    var body: some View {
        let summaries = stores.map(\.activitySummary)
        let shows = Self.shows(summaries)
        let stoppable = Self.stoppable(summaries)
        ControlGroup {
            Button {
                run(shows == .play ? .continueAll : .pauseAll)
            } label: {
                shows == .play
                    ? Label("Continue All", systemImage: "play.fill")
                    : Label("Pause All", systemImage: "pause.fill")
            }
            .help(shows == .play ? "Continue the work Pause All paused" : "Pause all work in every open project")
            .disabled(shows == .none)
            .accessibilityIdentifier("activity.runControls.playPause")

            Button { confirmingStop = true } label: { Label("Stop All", systemImage: "stop.fill") }
                .help("Stop all work in every open project")
                .disabled(stoppable == 0)
                .accessibilityIdentifier("activity.runControls.stop")
        }
        .confirmationDialog(Self.stopQuestion(stoppable), isPresented: $confirmingStop) {
            Button("Stop All", role: .destructive) { run(.stopAll) }
        } message: {
            Text("What they have done is kept; Retry runs them again.")
        }
        .help(notice ?? "")
    }

    private func run(_ control: ActivityRunControl) {
        let stores = stores
        Task {
            var failure: String?
            for store in stores {
                if let error = await store.runControl(control) { failure = failure ?? error }
            }
            notice = failure
        }
    }
}

#Preview("Run controls") {
    ActivityRunControlsButtons()
        .environment(LibraryManager.shared)
        .padding()
}
