import Foundation

/// Pure, testable helper for building breadcrumb paths from document hierarchies.
/// Converts a document selection into a readable trail: "Library › Folder › File › p.4"
struct BreadcrumbBuilder {
    typealias DocumentLookup = (String) -> Document?

    private init() { }

    /// Build a breadcrumb trail from a document and its parent hierarchy.
    /// Returns a string like "Library › Folder › File › p.4" or just the document name
    /// if hierarchy is empty.
    static func buildBreadcrumb(
        from document: Document,
        parentLookup: DocumentLookup,
        pageLabel: String? = nil
    ) -> String {
        var path: [String] = []
        var current: Document? = document

        // Traverse up the parent chain
        while let doc = current {
            path.insert(doc.name, at: 0)
            if let parentId = doc.parentId {
                current = parentLookup(parentId)
            } else {
                current = nil
            }
        }

        // Add library root if path is not empty
        if !path.isEmpty {
            path.insert("Library", at: 0)
        }

        // Add page label if provided
        if let pageLabel {
            path.append(pageLabel)
        }

        return path.joined(separator: " › ")
    }

    /// Build breadcrumb for the current selection state in library mode.
    /// Returns just the leaf name if no parent hierarchy exists (minimal display).
    /// Returns full trail if hierarchy is present.
    static func buildBreadcrumbForLibraryMode(
        document: Document?,
        pageLabel: String? = nil,
        parentLookup: DocumentLookup
    ) -> String {
        guard let doc = document else {
            return "Library"
        }

        // Check if this document has a parent — if not, just return the name
        if doc.parentId == nil && pageLabel == nil {
            return doc.name
        }

        // Full breadcrumb with hierarchy
        return buildBreadcrumb(from: doc, parentLookup: parentLookup, pageLabel: pageLabel)
    }
}
