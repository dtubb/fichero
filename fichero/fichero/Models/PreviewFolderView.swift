import Foundation

/// How a Preview pane shows a selected folder (#6365, `library.preview.folder-view-per-pane`).
/// Stored on the pane as `PaneConfig.previewFolderView` (the raw string), so a renamed case never
/// breaks a saved workspace: an unknown string reads as the default.
/// The cases are in the order "Show folder as" lists them: List, Table, Icons, Canvas (#6562).
enum PreviewFolderView: String, CaseIterable, Identifiable, Sendable {
    case list
    case table
    case icons
    case canvas

    var id: String { rawValue }

    /// Table, the first-open view the owner ruled in #6172
    /// (`library.preview.folder-view-defaults`); the canvas stops being forced.
    static let defaultView: PreviewFolderView = .table

    /// The view a pane shows: its stored choice, or the default when never chosen or unreadable.
    static func effective(_ raw: String?) -> PreviewFolderView {
        raw.flatMap(PreviewFolderView.init(rawValue:)) ?? defaultView
    }

    /// Whether this pane draws the selection through its folder view at all. A file, a page or a
    /// multiple selection is shown as today whatever the folder view is, and the choice is kept for
    /// the next folder (`library.preview.folder-view-cannot-show-says-so`).
    static func applies(selectionIsSingleFolder: Bool) -> Bool { selectionIsSingleFolder }

    var title: String {
        switch self {
        case .canvas: "Canvas"
        case .list: "List"
        case .table: "Table"
        case .icons: "Icons"
        }
    }

    var icon: String {
        switch self {
        case .canvas: "square.grid.3x3.topleft.filled"
        case .list: "list.bullet"
        case .table: "tablecells"
        case .icons: "square.grid.2x2"
        }
    }

    /// The `LibraryView` display mode for the row and icon views; nil for the canvas.
    var displayMode: ViewDisplayMode? {
        switch self {
        case .canvas: nil
        case .list: .list
        case .table: .table
        case .icons: .icon
        }
    }
}
