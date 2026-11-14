//
//  RunAutomaticallySetting.swift
//  Fichero
//
//  Run Automatically is a SETTING, in one place (`activity.automatic.one-place`, `activity.pane.run-automatically-is-a-setting`,
//  #6441; owner 2026-11-13): Settings › General, a plain label and one sentence. The engine's background mode is what it sets
//  (`ActivityStore.setBackgroundMode`): on = automatic, off = paused. The old "Run Now" sense (go ahead although the Mac is in
//  use) is a one-off verb elsewhere, not a mode here.
//

import SwiftUI

enum RunAutomaticallySetting {
    static let label = "Run automatically"
    static let sentence = "Fichero processes new and changed pages in the background: thumbnails, text, names and search."

    /// The switch's position for the engine's mode: `started` (Run Now, one-off) still reads as on.
    static func isOn(_ mode: ActivityMode) -> Bool { mode != .paused }

    /// The mode the switch sets: on is automatic (never `started`: that is the one-off verb), off pauses background work.
    static func mode(isOn: Bool) -> ActivityMode { isOn ? .automatic : .paused }
}

/// The one toggle, for Settings › General; a project's own copy (Use the app's setting / On / Off) follows.
struct RunAutomaticallyToggle: View {
    let store: ActivityStore
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Toggle(RunAutomaticallySetting.label, isOn: Binding(
                get: { RunAutomaticallySetting.isOn(store.backgroundMode) },
                set: { isOn in Task { failure = await store.setBackgroundMode(RunAutomaticallySetting.mode(isOn: isOn)) } }
            ))
            .accessibilityIdentifier("settings.general.run-automatically")
            Text(RunAutomaticallySetting.sentence).font(.caption).foregroundStyle(.secondary)
            if let failure {
                Label(failure, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(.orange)
            }
        }
    }
}

#Preview("Run automatically") {
    let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/Preview.fichero",
                               session: URLSession(configuration: .ephemeral))
    Form {
        Section("Background Work") {
            RunAutomaticallyToggle(store: ActivityStore(service: ActivityService(ficheroClient: client), library: nil))
        }
    }
    .formStyle(.grouped).frame(width: 420)
}
