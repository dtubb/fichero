import AppKit

/// Hold Option while Fichero launches to start with nothing open (maintainer, 2026-10-09):
/// forgets which projects were open and the saved window layout, so a launch that crashes on a
/// restored window (#5628) can be got past. Projects themselves are never touched.
enum StartFresh {
    /// AppKit reads this while restoring windows, after `applicationWillFinishLaunching`; set for
    /// this launch only and cleared again in `applicationDidFinishLaunching`.
    static let ignoreSavedStateKey = "ApplePersistenceIgnoreState"

    /// Window layout keys AppKit and SwiftUI keep in the app's defaults.
    static let layoutKeyPrefixes = ["NSWindow Frame", "NSSplitView Subview Frames", "NSToolbar Configuration",
                                    "NSNavPanel", "NSTableView", "NSOutlineView"]

    /// Asks when Option is held at launch; true when the person chose to start fresh.
    @MainActor static func askIfOptionHeld() -> Bool {
        guard NSEvent.modifierFlags.contains(.option) else { return false }
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
