//
//  StoppedAtQuitAlertModifier.swift
//  Fichero
//
//  Mounts the launch alert of `activity.launch.nothing-starts-one-alert` (#6584) over the main window: asked once per
//  project as it opens; Leave Paused is the default. On the Mac the alert is `presentPlatformAlert`'s sheet, because
//  SwiftUI's alert there keeps three buttons and drops the fourth (Delete All was never shown).
//

import SwiftUI

struct StoppedAtQuitAlertModifier: ViewModifier {
    @Environment(\.openWindow) private var openWindow
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    let libraryManager: LibraryManager
    @State private var alert = StoppedAtQuitAlert()

    private var libraries: [LibraryManager.LibraryReference] { libraryManager.openLibraries }

    func body(content: Content) -> some View {
        content
            .task(id: libraries.map(\.id)) { await alert.check(libraries: libraries) }
            #if os(macOS)
            .onChange(of: alert.isPresented) { _, shown in
                if shown { presentSheet() }
            }
            #else
            .alert(alert.title, isPresented: Bindable(alert).isPresented) {
                ForEach(StoppedAtQuitAlert.Choice.allCases, id: \.self) { choice in
                    Button(choice.title, role: choice.isDestructive ? .destructive : nil) { answer(choice) }
                        .keyboardShortcut(choice == .leavePaused ? .defaultAction : nil)
                }
            } message: {
                Text(alert.message)
            }
            #endif
    }

    private func answer(_ choice: StoppedAtQuitAlert.Choice) {
        Task {
            await alert.answer(choice, libraries: libraries, steps: windowSteps) { picked in
                ActivityWindowSelectionState.shared.revealAll = picked
                openWindow(id: ActivityWindowSelectionState.monitorWindowID)
            }
        }
    }

    #if os(macOS)
    /// The four answers as one sheet alert (the platform bridge's, which holds every button).
    private func presentSheet() {
        let choices = StoppedAtQuitAlert.Choice.allCases
        presentPlatformAlert(title: alert.title, message: alert.message,
                             buttons: choices.map { ($0.title, $0.isDestructive) }) { index in
            answer(choices.indices.contains(index) ? choices[index] : .leavePaused)
        }
    }
    #endif
}
