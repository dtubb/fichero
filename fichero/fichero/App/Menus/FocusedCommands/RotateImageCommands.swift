import SwiftUI

// MARK: - Rotate Left ⌘L / Rotate Right ⌘R (#5304, library.rotate.command-r-and-l)

/// The images a rotate acts on: the selected ones, or the card chosen on a folder's canvas in the
/// Preview. Only images: the engine's rotate is an image edit (`/api/images/{id}/operations/rotate`,
/// the image editor's own Rotate buttons), and a PDF page or a folder has no image chain to edit.
///
/// File scope so Swift Testing can call it off-main.
func rotatableImageIds(selection: Set<String>, canvasFocus: Document?, lookUp: (String) -> Document?) -> [String] {
    if let canvasFocus, canvasFocus.fileType == .image { return [canvasFocus.id] }
    return selection.sorted().filter { lookUp($0)?.fileType == .image }
}

extension FocusedValues {
    /// ⌘L — rotate the selected images 90° to the left, in any pane of the focused window.
    @Entry var rotateImagesLeft: FocusedLibraryAction?
    /// ⌘R — rotate the selected images 90° to the right.
    @Entry var rotateImagesRight: FocusedLibraryAction?
}

/// Rotate Left and Rotate Right, as Apple Preview has them (⌘L, ⌘R), acting on the focused
/// window's selected images wherever they are shown: library, Preview, canvas.
struct RotateImageMenuSection: View {
    @FocusedValue(\.rotateImagesLeft) private var left
    @FocusedValue(\.rotateImagesRight) private var right

    var body: some View {
        Button("Rotate Left") { left?.run() }
            .keyboardShortcut("l", modifiers: .command)
            .disabled(left?.isEnabled != true)
        Button("Rotate Right") { right?.run() }
            .keyboardShortcut("r", modifiers: .command)
            .disabled(right?.isEnabled != true)
    }
}

// MARK: - Group / Ungroup (#5303)

/// The images a Group gathers into one group node (a letter of several pages): the cards selected on
/// a folder's canvas in the Preview when there are any, else the selected items; images only, as the
/// library's Group as Stack takes them, and at least two.
func groupableImageIds(selection: Set<String>, canvasSelection: [Document], lookUp: (String) -> Document?) -> [String] {
    let canvasImages = canvasSelection.filter { $0.fileType == .image }.map(\.id)
    let ids = canvasImages.count >= 2
        ? canvasImages
        : selection.sorted().filter { lookUp($0)?.fileType == .image }
    return ids.count >= 2 ? ids : []
}

extension FocusedValues {
    /// Group — gather the selected images into one group node (#5303).
    @Entry var groupSelectedItems: FocusedLibraryAction?
    /// Ungroup — return a selected group's members to where they were.
    @Entry var ungroupSelectedItem: FocusedLibraryAction?
}

/// Group / Ungroup in the Edit menu. The same group node the library's "Group as Stack" makes: one item that
/// holds its pages, reversibly.
struct GroupItemsMenuSection: View {
    @FocusedValue(\.groupSelectedItems) private var group
    @FocusedValue(\.ungroupSelectedItem) private var ungroup

    var body: some View {
        // No chords yet: ⌥⌘G, the Keynote/Freeform Group chord, is the Preview markup Line tool
        // (PreviewMarkupToolsRow). Whether Group takes it back is the maintainer's call (#5303).
        Button("Group") { group?.run() }
            .disabled(group?.isEnabled != true)
        Button("Ungroup") { ungroup?.run() }
            .disabled(ungroup?.isEnabled != true)
    }
}
