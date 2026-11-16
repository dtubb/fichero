import FicheroAPIClient

/// "What to check" on the Read stage's card (`designer.how.what-to-check`): the pages the reader is least sure of, least sure first, each
/// opened in the Reader by one press. The engine names and orders them; this only words them.
extension ActivityDetails {
    struct ToCheckRow: Equatable, Identifiable {
        let id: String  // the page's document id
        let text: String
    }

    static func toCheckRows(_ pages: [Components.Schemas.PageToCheck]) -> [ToCheckRow] {
        pages.enumerated().map { index, page in
            let lines = page.lines == 1 ? "1 line" : "\(page.lines) lines"
            let unsure = page.lineUnsureWords
            return ToCheckRow(id: page.pageId, text: "\(index + 1). \(Int((page.certainty * 100).rounded()))% sure · \(unsure) of \(lines)")
        }
    }
}

private extension Components.Schemas.PageToCheck {
    /// "3 unsure" among the page's lines.
    var lineUnsureWords: String { "\(linesUnsure) unsure" }
}
