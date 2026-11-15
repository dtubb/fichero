//
//  StoppedAtQuitAlertModifier.swift
//  Fichero
//
//  Mounts the launch alert of `activity.launch.nothing-starts-one-alert` (#6584) over the main window: asked once per
//  project as it opens; Leave Paused is the default. On the Mac the alert is an `NSAlert` sheet, because SwiftUI's
//  alert there keeps three buttons and drops the fourth (Delete All was never shown).
//

import SwiftUI
#if os(macOS)
import AppKit
#endif

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
            await alert.answer(choice, libraries: libraries, steps: windowSteps) {
                openWindow(id: ActivityWindowSelectionState.monitorWindowID)
            }
        }
    }

    #if os(macOS)
    /// The four answers as one AppKit alert, a sheet on the front window (app-modal when there is none).
    private func presentSheet() {
        let sheet = NSAlert()
        sheet.messageText = alert.title
        sheet.informativeText = alert.message
        let choices = StoppedAtQuitAlert.Choice.allCases
        for choice in choices {
            let button = sheet.addButton(withTitle: choice.title)
            button.hasDestructiveAction = choice.isDestructive
        }
        let finish: (NSApplication.ModalResponse) -> Void = { response in
            let index = response.rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
            answer(choices.indices.contains(index) ? choices[index] : .leavePaused)
        }
        if let window = NSApp.keyWindow ?? NSApp.mainWindow ?? NSApp.windows.first(where: \.isVisible) {
            sheet.beginSheetModal(for: window, completionHandler: finish)
        } else {
            finish(sheet.runModal())
        }
    }
    #endif
}
