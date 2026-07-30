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
        // Names come from `DocumentTitle`, never from `Document.name` directly:
        // a page child's name is the engine's upload temp file, so the trail
        // read `… › fichero_upload_c84fgjke.pdf` for a document the sidebar
        // called `18590129.pdf` (#4416).
        segments += chain.map { doc in
            Segment(
                name: DocumentTitle.displayName(
                    for: doc, parent: doc.parentId.flatMap(parentLookup)
                ),
                documentId: doc.id,
                isRoot: false
            )
        }

        // A page already appears as the trail's leaf via `displayName`, so an
        // appended label would repeat it — the doubled "Page 1" (#4416).
        if let pageLabel, chain.last?.docType != .page {
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
        var isLeaf = true
        var leafIsPage = false

        // Traverse up the parent chain, naming each step through DocumentTitle
        // so a page never contributes its storage filename (#4416).
        while let doc = current {
            let parent = doc.parentId.flatMap(parentLookup)
            path.insert(DocumentTitle.displayName(for: doc, parent: parent), at: 0)
            if isLeaf {
                leafIsPage = doc.docType == .page
                isLeaf = false
            }
            current = parent
        }

        // Add library root if path is not empty
        if !path.isEmpty {
            path.insert("Library", at: 0)
        }

        // Only when the leaf is not already the page (#4416): otherwise the
        // page number lands in the trail twice.
        if let pageLabel, !leafIsPage {
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
            return DocumentTitle.displayName(for: doc)
        }

        // Full breadcrumb with hierarchy
        return buildBreadcrumb(from: doc, parentLookup: parentLookup, pageLabel: pageLabel)
    }
}
