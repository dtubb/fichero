import Foundation

/// Pure, testable helper for building breadcrumb paths from document hierarchies.
/// Converts a document selection into a readable trail: "Library › Folder › File › p.4"
struct BreadcrumbBuilder {
    typealias DocumentLookup = (String) -> Document?

    private init() { }

    /// One clickable segment of the content-header breadcrumb (#1928).
    struct Segment: Equatable, Identifiable {
        let name: String
        /// The document to navigate to when tapped, or nil. `isRoot` marks the
        /// leading "Library" segment (navigates to the library root); a nil
        /// `documentId` on a non-root segment is a non-navigable leaf (a page label).
        let documentId: String?
        let isRoot: Bool

        var id: String { isRoot ? "root" : (documentId ?? "leaf:\(name)") }
        var isNavigable: Bool { isRoot || documentId != nil }
    }

    /// Build clickable breadcrumb segments: Library ▸ folder ▸ … ▸ document ▸ page.
    /// Pure — the same parent-chain walk as `buildBreadcrumb`, but structured so
    /// the header can render each segment as a button (#1928). A `guardCount`
    /// bounds a malformed (cyclic) parent chain.
    static func buildSegments(
        from document: Document?,
        parentLookup: DocumentLookup,
        pageLabel: String? = nil
    ) -> [Segment] {
        var segments = [Segment(name: "Library", documentId: nil, isRoot: true)]
        guard let document else { return segments }

        var chain: [Document] = []
        var current: Document? = document
        var guardCount = 0
        while let doc = current, guardCount <= 256 {
            chain.insert(doc, at: 0)
            current = doc.parentId.flatMap(parentLookup)
            guardCount += 1
        }
        segments += chain.map { Segment(name: $0.name, documentId: $0.id, isRoot: false) }

        if let pageLabel {
            segments.append(Segment(name: pageLabel, documentId: nil, isRoot: false))
        }
        return segments
    }

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
