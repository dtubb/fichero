import Foundation

/// The Mac Preview's way into the full-screen page (`preview.full-screen-page`, #6560): the same full-window reader
/// ⌃⌘R opens (`ImmersiveReaderView`), entered from the Preview head for the page or image the Preview is showing.
enum PreviewFullScreen {
    /// Whether the head offers "View Full Screen": only for one page or image, the things the reader shows.
    static func canEnter(shown: Document?, selectionCount: Int) -> Bool {
        guard let shown, selectionCount <= 1 else { return false }
        return shown.fileType == .image || shown.docType == .page
    }
}
