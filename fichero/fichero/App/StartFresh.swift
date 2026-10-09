#if os(macOS)
import AppKit

/// Hold Shift while Fichero launches to start with nothing open (maintainer, 2026-10-09; Shift is
/// macOS's own "don't reopen windows" key, and Option already opens the server chooser, #2381):
/// forgets which projects were open and the saved window layout, so a launch that crashes on a
/// restored window (#5628) can be got past. Projects themselves are never touched.
enum StartFresh {
    /// AppKit reads this while restoring windows, after `applicationWillFinishLaunching`; set for
    /// this launch only and cleared again in `applicationDidFinishLaunching`.
    static let ignoreSavedStateKey = "ApplePersistenceIgnoreState"

    /// Window layout keys AppKit and SwiftUI keep in the app's defaults.
    static let layoutKeyPrefixes = ["NSWindow Frame", "NSSplitView Subview Frames", "NSToolbar Configuration",
                                    "NSNavPanel", "NSTableView", "NSOutlineView"]

    /// Asks when Shift is held at launch; true when the person chose to start fresh.
    @MainActor static func askIfShiftHeld() -> Bool {
        guard NSEvent.modifierFlags.contains(.shift) else { return false }
        let alert = NSAlert()
        alert.messageText = "Start with nothing open?"
        alert.informativeText = "Fichero will open no projects and forget its window sizes and layout. "
            + "Your projects are not changed; open them again from File › Open."
        alert.addButton(withTitle: "Start Fresh")
        alert.addButton(withTitle: "Open as Usual")
        return alert.runModal() == .alertFirstButtonReturn
    }

    /// Forgets the open projects and the window layout.
    @MainActor static func reset(standard: UserDefaults = .standard, appDefaults: UserDefaults = EngineConfig.defaults) {
        appDefaults.removeObject(forKey: LibraryManager.openLibraryPathsKey)
        for key in standard.dictionaryRepresentation().keys where isLayoutKey(key) {
            standard.removeObject(forKey: key)
        }
        standard.set(true, forKey: ignoreSavedStateKey)
    }

    static func isLayoutKey(_ key: String) -> Bool {
        layoutKeyPrefixes.contains { key.hasPrefix($0) }
    }
}
#endif
