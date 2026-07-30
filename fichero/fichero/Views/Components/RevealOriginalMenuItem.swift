import SwiftUI

// MARK: - Show Original in Finder (#4305)

/// Pure policy for the "reveal the source file in Finder" context-menu item —
/// shared by every surface (sidebar rows, library grid, detail pane) so the
/// menus can't drift.
///
/// Remote-server safe: `document.path` is a path on the SERVER's machine, so
/// the item only appears when the engine is local (#1861) AND the path
/// actually resolves on this machine — a linked original may have been moved
/// or deleted since import.
enum RevealOriginalPolicy {
    /// The path Finder should reveal, or nil to omit the menu item entirely.
    static func revealablePath(
        path: String?,
        engineIsLocal: Bool,
        fileExists: (String) -> Bool
    ) -> String? {
        guard engineIsLocal, let path, !path.isEmpty, fileExists(path) else { return nil }
        return path
    }

    /// Finder-alias convention: a LINKED import is a pointer to an original,
    /// so the verb is "Show Original in Finder"; a copied/owned file is just
    /// revealed.
    static func label(isLinked: Bool) -> String {
        isLinked ? "Show Original in Finder" : "Reveal in Finder"
    }
}

/// The shared menu item. Renders nothing when the policy says the original
/// is not reachable from this machine (remote engine, missing file, folder
/// rows with no path).
struct RevealOriginalMenuItem: View {
    let document: Document

    var body: some View {
        #if os(macOS)
        if let path = RevealOriginalPolicy.revealablePath(
            path: document.path,
            engineIsLocal: EngineConfig.engineIsLocal,
            fileExists: { FileManager.default.fileExists(atPath: $0) }
        ) {
            Button {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            } label: {
                Label(RevealOriginalPolicy.label(isLinked: document.isLinked), systemImage: "folder")
            }
        }
        #endif
    }
}
