import Foundation

/// The name a new alias is CREATED with (#116).
///
/// This is a different problem from every other name defect found today, and
/// the difference is the whole reason it has its own type. #4416's leaks were
/// DISPLAY problems: the wrong text on screen, fixed by rendering differently,
/// and fixed retroactively for every existing document the moment the composer
/// changed. Alias creation PERSISTS the name it composes — it writes a row into
/// the engine. A storage filename that gets in here is data, not a label: it
/// survives the fix, it syncs, it exports, and the only way to correct it
/// afterwards is for a human to rename every affected row by hand.
///
/// Four call sites were writing `"\(doc.name) alias"` or `source?.name`
/// straight through — two in the sidebar's drop handlers, one in the sidebar's
/// context menu, and one in the LIBRARY's context menu, which is why the
/// sidebar-scoped audit only found three of them. All four now compose here.
///
/// `DocumentTitle.displayName` is the same ladder every display surface uses,
/// so an alias is named what the user SEES the document called — which is the
/// only answer that is stable when the underlying storage name is an upload id.
enum AliasName {

    /// The name for an alias of `document` being created under `targetParentId`.
    ///
    /// The " alias" suffix is appended only when the new row lands beside the
    /// original, because that is the case where two identically-named rows
    /// would otherwise sit next to each other. Dropping into a DIFFERENT folder
    /// keeps the plain name — Finder's behaviour, and the rule the sidebar drop
    /// handlers already encoded before this type existed.
    static func forAlias(
        of document: Document?,
        targetParentId: String?,
        parent: Document? = nil
    ) -> String {
        guard let document else { return DocumentTitle.placeholder }
        let base = DocumentTitle.displayName(for: document, parent: parent)
        return document.parentId == targetParentId ? "\(base) alias" : base
    }
}
