import Foundation

extension Document {
    /// Label to show beneath a PDF page thumbnail / as a page row's title.
    ///
    /// A page child document's `name` is an internal id / source filename
    /// ("page_0003", a hash), not something a reader recognizes — so for
    /// page rows we show the human **page number** instead: the 1-based
    /// `sequence` the backend stamps on each child. When the backend later
    /// exposes an extracted `page_label` (e.g. "iv", "Plate 3") we prefer
    /// that over the raw number — that field is added to the page model by
    /// #2080; until it lands this resolves to the numeric page only.
    ///
    /// Returns `nil` for non-page documents so callers fall back to `name`.
    /// Scoped to `docType == .page` so top-level documents and non-PDF
    /// items are never relabeled.
    var pageThumbnailLabel: String? {
        guard docType == .page, let pageNumber = sequence else { return nil }
        // #2080: prefer a non-empty extracted `page_label` here, i.e.
        //   `pageLabel?.nonEmpty ?? "\(pageNumber)"`
        return "\(pageNumber)"
    }
}
