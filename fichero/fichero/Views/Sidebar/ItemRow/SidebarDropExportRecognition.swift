import Foundation

// MARK: - Recognising OUR OWN export by its file URL alone (#4401)

/// The temp-directory prefix `SidebarDragID.exportSourceFile` writes into when
/// a document row is dragged. Distinct from `fichero-drop-`, which is where an
/// INBOUND external drop's bytes are staged — the two must not be confused.
let ficheroInternalDragExportPrefix = "fichero-drag-"

/// Is this URL a copy THIS APP just made of a document already in the library?
///
/// The provider-reading classifier above is the primary defence and identifies
/// an internal drag positively, by the id it carries. This predicate exists for
/// the one route that cannot ask: a `.dropDestination(for: URL.self)`, which is
/// handed resolved URLs and never sees the providers behind them.
///
/// That route is not hypothetical. `DropTargetModifiers` mounts such a
/// destination on the WHOLE `NavigationSplitView` — sidebar column and detail
/// column both — and since #4123 a document row exports a real file. So an
/// internal drag released anywhere the nested per-row handlers do not claim
/// (sidebar whitespace, the gaps between sections, the content pane) resolved
/// to that exported file and was IMPORTED: a second, hollow copy of a document
/// already in the library. That is #4401's exact shape, in the widest-scope
/// drop target in the app, and it is why the symptom outlived the fixes to the
/// row-level paths — those only cover drops that land on a row.
///
/// A URL under this prefix is by construction a copy of something already
/// stored. Re-ingesting it can never be right.
func isFicheroInternalDragExport(_ url: URL) -> Bool {
    url.pathComponents.contains { $0.hasPrefix(ficheroInternalDragExportPrefix) }
}

/// Split dropped URLs into the ones that are genuinely external and the ones
/// this app exported for its own drag. Pure, so the rule is testable without a
/// live drag — the gap that let this survive three rounds of fixes.
func partitionFicheroInternalDragExports(
    _ urls: [URL]
) -> (external: [URL], internalExports: [URL]) {
    var external: [URL] = []
    var internalExports: [URL] = []
    for url in urls {
        if isFicheroInternalDragExport(url) {
            internalExports.append(url)
        } else {
            external.append(url)
        }
    }
    return (external, internalExports)
}
