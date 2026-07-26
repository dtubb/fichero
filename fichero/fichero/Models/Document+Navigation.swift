import Foundation

// MARK: - Navigation

extension Document {
    /// True if double-clicking should navigate *into* this document
    /// (show its children) rather than preview it.
    ///
    /// Containers in 0.0.2:
    ///   - Folders — children are the folder's contents
    ///   - PDFs — children are one `Document` per page (see #568)
    var isNavigableContainer: Bool {
        if docType == .folder { return true }
        if fileType == .pdf { return true }
        return false
    }
}
