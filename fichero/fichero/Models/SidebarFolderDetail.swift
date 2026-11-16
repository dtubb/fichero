import Foundation

/// What a sidebar folder click does to the window's detail document (#4228, `read.a-click-shows-its-folder-at-once`).
/// It cleared the detail first, then set the folder: two changes per click, each running the whole detail cascade
/// (Inspector, toolbar context, Preview). The clear exists for one case only (#795): a folder that must be fetched,
/// so the old file's detail does not linger meanwhile. A folder already in hand is applied in one change.
enum SidebarFolderDetail: Equatable {
    /// The detail already is this folder: nothing to write.
    case keep
    /// The folder is in hand: one write.
    case apply
    /// The folder must be fetched: clear now, apply when it arrives.
    case clearThenFetch

    static func plan(currentDetailId: String?, folderId: String, inHand: Bool) -> SidebarFolderDetail {
        if currentDetailId == folderId { return .keep }
        return inHand ? .apply : .clearThenFetch
    }
}
