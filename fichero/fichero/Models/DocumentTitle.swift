import Foundation

/// The one place a document's user-facing name is decided (#4416).
///
/// The island read `Local › Page 1 — fichero_upload_c84fgjke.pdf - Page 1`
/// for a document the sidebar called `18590129.pdf`. Two defects, one cause.
///
/// **The name.** `fichero_upload_<random>` is the temp file `save_uploaded_file`
/// writes, and `ingest_file` derives `Document.name` from the path. The engine
/// corrects that back to the user's filename (#1104) — but only for the
/// document that was uploaded. Its PAGE children are created from the same temp
/// path and never fixed up, so a page's `name` is a storage artifact. For
/// archival material the real filename is often the only human-readable
/// identity a scan has: `18590129.pdf` is the date 1859-01-29. Showing the
/// temp name puts the least meaningful string where the user looks to know
/// where they are.
///
/// **The doubling.** `toolbarTitle` composed `"Page 1 — <name>"` while the
/// breadcrumb separately appended a page label, with a different separator.
/// Two composers, so the page appeared twice.
///
/// Both are fixed by making the LEAF name page-aware and composing once: the
/// title is the leaf, the breadcrumb is the trail, and the page number lives in
/// exactly one of them.
enum DocumentTitle {

    /// Prefix of the engine's upload temp file (`db/storage.py`). A name
    /// starting with this is never user-facing — it is an implementation
    /// detail that leaked, the same defect class as a raw `doc:` id appearing
    /// in a list row (#4398).
    static let storageNamePrefix = "fichero_upload_"

    /// Shown when nothing honest is available. Never an id, never a path.
    static let placeholder = "Untitled"

    /// Whether this name is the engine's storage artifact rather than
    /// something the user chose or recognises.
    static func isStorageName(_ name: String) -> Bool {
        name.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix(storageNamePrefix)
    }

    /// The name to show for `document`, given its parent when known.
    ///
    /// Order is by how much the user would recognise it:
    ///   1. an explicit metadata title — someone named this deliberately
    ///   2. the page number, for a page — a page's own `name` is a storage
    ///      artifact, and "Page 4" is what a reader calls it
    ///   3. its own name, unless that is the storage artifact
    ///   4. the parent's name — a page of `18590129.pdf` is at least that
    ///   5. `placeholder`
    ///
    /// The storage name and the id are not in the list at any position: an
    /// honest "Untitled" is better than a true-but-meaningless identifier.
    static func displayName(for document: Document, parent: Document? = nil) -> String {
        if let title = metadataTitle(document) { return title }

        if document.docType == .page, let label = document.pageThumbnailLabel {
            return "Page \(label)"
        }

        let own = document.name.trimmingCharacters(in: .whitespacesAndNewlines)
        if !own.isEmpty, !isStorageName(own) { return own }

        if let parent {
            let parentName = parent.name.trimmingCharacters(in: .whitespacesAndNewlines)
            if !parentName.isEmpty, !isStorageName(parentName) { return parentName }
        }

        return placeholder
    }

    /// A deliberately-set title from metadata, if there is one.
    static func metadataTitle(_ document: Document) -> String? {
        guard let raw = document.metadata["title"]?.value as? String else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// The window/island title for the current selection.
    ///
    /// Deliberately the LEAF only. The path lives in the breadcrumb subtitle,
    /// so composing "<parent> — <page>" here is what put the page on screen
    /// twice. One page component, in one place.
    static func windowTitle(
        leaf: Document?,
        parent: Document? = nil,
        selectedPageCount: Int = 0
    ) -> String {
        if selectedPageCount > 1 {
            return "\(selectedPageCount) pages"
        }
        guard let leaf else { return placeholder }
        return displayName(for: leaf, parent: parent)
    }

    /// Shorten a long name for a length-constrained surface, keeping the start
    /// and the extension so `NCM_Diary_19240101-…pdf` stays identifiable.
    ///
    /// Truncating the tail would drop the extension, and truncating the head
    /// would drop the date or folio that identifies an archival scan — the two
    /// ends are the parts that carry meaning.
    static func middleTruncated(_ name: String, limit: Int) -> String {
        guard limit > 1, name.count > limit else { return name }

        let ellipsis = "…"
        let dotIndex = name.lastIndex(of: ".")
        let suffix: String = if let dotIndex, name.distance(from: dotIndex, to: name.endIndex) <= 6 {
            String(name[dotIndex...])
        } else {
            ""
        }

        let headroom = limit - suffix.count - ellipsis.count
        guard headroom > 0 else { return String(name.prefix(limit - 1)) + ellipsis }
        return String(name.prefix(headroom)) + ellipsis + suffix
    }
}
