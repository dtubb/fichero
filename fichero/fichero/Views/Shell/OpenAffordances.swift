#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

#if os(macOS)

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
        manager.pendingWindowLibraryIds.append(libraryId)
        manager.pendingOpenDocumentId = documentId

        let hostWindow = NSApp.keyWindow ?? NSApp.mainWindow

        // Snapshot existing windows so we can identify the newly created one
        // for tab-merging below.
        let before = Set(NSApp.windows.map(ObjectIdentifier.init))
        // Both a new window and a native tab open the SAME `openWindow(id: "main")`
        // scene, whose `.task` runs `connectBackend(restart: false)` — so the tab
        // reuses the app-level connection via the #3394 start-guard exactly like a
        // window (no re-auth / no backend restart). The `addTabbedWindow` merge
        // below is pure AppKit window management and never touches the backend.
        // This is the direct native-tab path (`addTabbedWindow` is the only macOS
        // API for it), not a new-window-then-hide workaround (#3407).
        if asTab {
            openWindow(id: "main")
        } else {
            openWindowDisallowingAutomaticTabs(using: openWindow, before: before)
        }

        guard asTab else { return }
        guard let hostWindow else { return }

        // SwiftUI materialises the new NSWindow on a later runloop turn, so
        // defer the tab-merge until it exists.
        DispatchQueue.main.async {
            let newWindow = newlyCreatedWindow(afterOpeningWindows: before, hostWindow: hostWindow)
            guard let newWindow else { return }
            hostWindow.tabbingMode = .preferred
            newWindow.tabbingMode = .preferred
            hostWindow.addTabbedWindow(newWindow, ordered: .above)
            newWindow.makeKeyAndOrderFront(nil)
        }
    }

    @MainActor
    private static func openWindowDisallowingAutomaticTabs(
        using openWindow: OpenWindowAction,
        before: Set<ObjectIdentifier>
    ) {
        let previousAllowsAutomaticTabbing = NSWindow.allowsAutomaticWindowTabbing
        NSWindow.allowsAutomaticWindowTabbing = false
        openWindow(id: "main")
        DispatchQueue.main.async {
            NSWindow.allowsAutomaticWindowTabbing = previousAllowsAutomaticTabbing
            if let newWindow = NSApp.windows.first(where: {
                !before.contains(ObjectIdentifier($0)) && $0.isVisible
            }) {
                newWindow.tabbingMode = .disallowed
            }
        }
    }

    @MainActor
    private static func newlyCreatedWindow(
        afterOpeningWindows before: Set<ObjectIdentifier>,
        hostWindow: NSWindow
    ) -> NSWindow? {
        NSApp.windows.first {
            !before.contains(ObjectIdentifier($0)) && $0.isVisible && $0 !== hostWindow
        }
    }
}

enum LibraryWindowOpener {
    @MainActor
    static func openOrFocusLibrary(at url: URL, using openWindow: OpenWindowAction) {
        let normalizedURL = url.standardizedFileURL
        Task {
            await KnownLibraryRegistryStore.shared.noteOpenedLibrary(
                url: normalizedURL,
                displayName: normalizedURL.deletingPathExtension().lastPathComponent
            )
        }
        guard !focusExistingWindow(for: normalizedURL) else { return }
        let manager = LibraryManager.shared
        let library = manager.openLibraries.first(where: {
            $0.url.standardizedFileURL == normalizedURL
        }) ?? manager.openLibrary(at: normalizedURL, makeCurrent: false)

        WindowOpener.open(libraryId: library.id, asTab: false, using: openWindow)
    }

    @MainActor
    private static func focusExistingWindow(for url: URL) -> Bool {
        let normalizedURL = url.standardizedFileURL
        guard let window = NSApp.windows.first(where: {
            $0.representedURL?.standardizedFileURL == normalizedURL
        }) else {
            return false
        }

        NSApp.activate(ignoringOtherApps: true)
        if window.isMiniaturized {
            window.deminiaturize(nil)
        }
        window.makeKeyAndOrderFront(nil)
        return true
    }
}

#else
// iOS stubs for the shared open affordances. These keep cross-platform call
// sites compiling; real iOS behavior (tabs / scene activation) will be added
// in a later bucket-D pass.

struct OpenInMenuItems: View {
    var open: (() -> Void)?
    let openInNewTab: () -> Void
    let openInNewWindow: () -> Void

    var body: some View {
        if let open {
            Button(action: open) {
                Label("Open", systemImage: "arrow.up.forward.app")
            }
        }
        Button(action: openInNewWindow) {
            Label("Open in New Window", systemImage: "macwindow.badge.plus")
        }
    }
}

enum WindowOpener {
    @MainActor
    static func open(
        libraryId: UUID,
        documentId: String? = nil,
        asTab: Bool,
        using openWindow: OpenWindowAction
    ) {
        // iOS: no native tabs; just open a new window scene.
        openWindow(id: "main")
    }
}

enum LibraryWindowOpener {
    @MainActor
    static func openOrFocusLibrary(at url: URL, using openWindow: OpenWindowAction) {
        // iOS: open the library in a new window scene; focus is scene-based.
        let manager = LibraryManager.shared
        let library = manager.openLibraries.first(where: {
            $0.url.standardizedFileURL == url.standardizedFileURL
        }) ?? manager.openLibrary(at: url, makeCurrent: false)
        WindowOpener.open(libraryId: library.id, asTab: false, using: openWindow)
    }
}
#endif
