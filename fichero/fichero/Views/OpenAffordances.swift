import AppKit
import SwiftUI

/// Finder-style "Open" affordances shared across library rows, sidebar rows,
/// and ontology rows (entities / claims). Renders **Open / Open in New Tab /
/// Open in New Window** menu items wired to caller-supplied closures so each
/// surface reuses its OWN existing in-window "open" path plus the shared
/// new-window path (`WindowOpener`). There is deliberately no parallel tab
/// system — this just surfaces the existing machinery. (#1685)
struct OpenInMenuItems: View {
    /// In-window open (e.g. show in detail pane / select). Omit when the
    /// surface has no distinct in-window open action.
    var open: (() -> Void)?
    let openInNewTab: () -> Void
    let openInNewWindow: () -> Void

    var body: some View {
        if let open {
            Button(action: open) {
                Label("Open", systemImage: "arrow.up.forward.app")
            }
        }
        Button(action: openInNewTab) {
            Label("Open in New Tab", systemImage: "plus.rectangle.on.rectangle")
        }
        Button(action: openInNewWindow) {
            Label("Open in New Window", systemImage: "macwindow.badge.plus")
        }
    }
}

/// Opens a new Fichero window on a given library, reusing the SAME path as the
/// File ▸ New Window command (`LibraryManager.currentLibraryId` +
/// `openWindow(id: "main")` — the Safari model). When `asTab` is true it
/// best-effort merges the freshly opened window into the key window's native
/// macOS tab group; if that merge can't be performed it simply opens as a
/// separate window (graceful fallback). (#1685)
enum WindowOpener {
    /// - Parameters:
    ///   - libraryId: Library the new window should view.
    ///   - documentId: Optional document to focus once the new window loads.
    ///   - asTab: When true, attempt to join the new window as a macOS tab.
    ///   - openWindow: The `@Environment(\.openWindow)` action from the caller.
    @MainActor
    static func open(
        libraryId: UUID,
        documentId: String? = nil,
        asTab: Bool,
        using openWindow: OpenWindowAction
    ) {
        let manager = LibraryManager.shared
        manager.currentLibraryId = libraryId
        manager.pendingOpenDocumentId = documentId

        // Snapshot existing windows so we can identify the newly created one
        // for tab-merging below.
        let before = Set(NSApp.windows.map(ObjectIdentifier.init))
        openWindow(id: "main")

        guard asTab else { return }

        // SwiftUI materialises the new NSWindow on a later runloop turn, so
        // defer the tab-merge until it exists.
        DispatchQueue.main.async {
            guard let host = NSApp.keyWindow ?? NSApp.mainWindow else { return }
            let newWindow = NSApp.windows.first {
                !before.contains(ObjectIdentifier($0)) && $0.isVisible && $0 !== host
            }
            guard let newWindow else { return }
            host.addTabbedWindow(newWindow, ordered: .above)
            newWindow.makeKeyAndOrderFront(nil)
        }
    }
}
