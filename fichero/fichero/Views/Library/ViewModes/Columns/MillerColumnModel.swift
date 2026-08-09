import Foundation
import SwiftUI

/// Pure path logic for the Finder-style Miller column browser
/// (#4160 step 4). The browse path is a chain of folder IDS below the
/// browsed root — ids, never `Document` snapshots, so every render resolves
/// each segment through the live `DocumentStore` and a rename/move/delete
/// mid-path can't leave the columns disagreeing with the sidebar.
enum MillerColumnModel {
    /// The longest prefix of `path` whose every id still resolves to a live
    /// FOLDER. A deleted / moved-away / no-longer-a-folder segment truncates
    /// the path at that depth — the sane recovery: everything above it is
    /// still valid, everything below it no longer exists.
    static func livePath(_ path: [String], resolve: (String) -> Bool) -> [String] {
        var live: [String] = []
        for id in path {
            guard resolve(id) else { break }
            live.append(id)
        }
        return live
    }

    /// Descend into `folderId` selected at column `depth`: keep the path
    /// ABOVE that column and make the folder the new deepest segment.
    /// Depth 0 is the root column (children of the browsed folder), so a
    /// selection at depth d keeps `d` path segments.
    static func descend(path: [String], atDepth depth: Int, into folderId: String) -> [String] {
        Array(path.prefix(max(0, depth))) + [folderId]
    }

    /// Truncate the path for a NON-folder selection at `depth` — deeper
    /// columns close, the selected document's column stays.
    static func truncate(path: [String], forSelectionAtDepth depth: Int) -> [String] {
        Array(path.prefix(max(0, depth)))
    }

    /// Clamp the active column to the columns that actually exist:
    /// path.count + 1 columns (root + one per segment).
    static func clampActiveDepth(_ depth: Int, pathCount: Int) -> Int {
        min(max(0, depth), max(0, pathCount))
    }
}

// The model has no view of its own — preview the columns browser it drives
// (Daniel, 2026-08-09: every view-mode file previews in place).
#Preview("Columns mode") { LibraryPreviewFixtures.mode(.columns, .columns) }
