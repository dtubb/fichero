import Foundation

enum WorkflowRunTarget: Hashable {
    case file(String)
    case folder(String)

    /// The row's OWN document id. This is the identity that always exists,
    /// whatever any client-side collection happens to hold, and it is what
    /// makes a cross-library row resolvable (#4419).
    var documentId: String {
        switch self {
        case let .file(id): return id
        case let .folder(id): return id
        }
    }

    /// The files this target runs on, as far as the loaded documents can say.
    ///
    /// A FILE row is its own target, unconditionally. It used to be gated on
    /// `documents.contains { $0.id == id }` — a presence test against
    /// `documentStore.sidebarDocuments`, i.e. the ACTIVE library's store. A row
    /// in another library (Marshall) is not in that store, so it failed the
    /// test, resolved to nothing, and the whole subtree lost its Run Workflow
    /// submenu. Whether a client cache happens to hold a document has no
    /// bearing on whether the engine can run it.
    ///
    /// A FOLDER row expands to every descendant file at ANY depth. It used to
    /// match `$0.parentId == path` — direct children only — so a run on a box
    /// containing archives containing folders reached nothing but the files
    /// sitting loose at the top. An empty return here is meaningful: it means
    /// the children are not loaded, and the caller falls back to the folder's
    /// own id rather than to nothing.
    fileprivate func fileIDs(from documents: [Document]) -> [String] {
        switch self {
        case let .file(id):
            return [id]
        case let .folder(id):
            return WorkflowRunTargetResolver.descendantFileIDs(of: id, in: documents)
        }
    }
}

/// Resolves the document scope for a context-menu workflow run (#4419).
///
/// Two rules, both learned the hard way:
///
/// **A clicked row always resolves to something.** The old resolver could
/// return an empty list — from a cross-library row, or a folder whose children
/// had not loaded — and the menu was gated on that list being non-empty, so the
/// affordance silently vanished. A missing menu is indistinguishable from an
/// unsupported feature, which is exactly how #4419 was reported: not "this row
/// fails" but "nothing in Marshall can be run".
///
/// **Narrowing is as bad as widening, and must be declared.** #4396 was the
/// client silently WIDENING a run to a whole folder; this is the client
/// silently NARROWING a multi-selection to one row, because the multi path was
/// taken only when `selection.contains(clicked)` — unreliable while #4377's
/// selection defects were live. Both come from scope being derived and never
/// stated. So the resolution carries what it did, and the menu says it.
enum WorkflowRunTargetResolver {

    struct Resolution: Equatable {
        /// Exactly the ids to run on. Never empty for a real clicked row.
        let targetIds: [String]

        /// The user had a selection and the clicked row was NOT part of it, so
        /// the run targets the clicked row alone. The menu must say so rather
        /// than quietly dropping the selection the user made.
        let ignoredSelection: Bool

        /// At least one target could not be expanded from the loaded documents
        /// and fell back to the row's own id — a cross-library row, or a folder
        /// whose children have not loaded. The run is still correct: the engine
        /// resolves a folder id itself.
        let usedRowIdentityFallback: Bool

        var isEmpty: Bool { targetIds.isEmpty }
    }

    /// Pick WHICH selection a run honours, from the two independent domains a
    /// sidebar right-click can see (#4552).
    ///
    /// The sidebar used to hand `resolve` the UNION of its own selected rows
    /// and the window's document selection. `resolve` then treats the clicked
    /// row being present anywhere in that set as "the user right-clicked
    /// inside their selection, so run on all of it". Across a union of two
    /// domains that inference is invalid: the clicked row can arrive from the
    /// WINDOW domain (it is simply what the gallery is previewing) while the
    /// extra ids come from the SIDEBAR domain (a row selected for some other
    /// reason, possibly an hour ago). Neither is a multi-selection the user
    /// made, but together they read as one.
    ///
    /// Measured on Daniel's 2026-08-05 reproduction: clicked `5765604b` with
    /// sidebar `{7dba0b73}` and window `{5765604b}` yielded
    /// `documents:2 [5765604b, 7dba0b73]` — a run on a PDF the user had not
    /// touched since the previous hour. The batch-picker surface, which has
    /// only ONE domain, was correct in the same library minutes apart.
    ///
    /// So: never union. A multi-target run happens only when the clicked row
    /// belongs to the domain supplying the other targets. When it belongs to
    /// neither, both are still returned so `resolve` can report
    /// `ignoredSelection` — it will not USE them, because `usesSelection` is
    /// false, but the menu must still say the selection was set aside.
    static func selectionScope(
        clicked: WorkflowRunTarget,
        sidebarSelection: Set<WorkflowRunTarget>,
        windowSelection: Set<WorkflowRunTarget>
    ) -> Set<WorkflowRunTarget> {
        if sidebarSelection.contains(clicked) { return sidebarSelection }
        if windowSelection.contains(clicked) { return windowSelection }
        return sidebarSelection.union(windowSelection)
    }

    static func resolve(
        clicked: WorkflowRunTarget,
        selection: Set<WorkflowRunTarget>,
        documents: [Document]
    ) -> Resolution {
        let usesSelection = selection.contains(clicked)
        let targets: [WorkflowRunTarget] = usesSelection ? Array(selection) : [clicked]
        let ignoredSelection = !usesSelection && !selection.isEmpty

        var ids = Set<String>()
        var usedFallback = false
        for target in targets {
            let expanded = target.fileIDs(from: documents)
            if expanded.isEmpty {
                // NEVER resolve to nothing. The row's own identity is a target
                // the engine can act on.
                ids.insert(target.documentId)
                usedFallback = true
            } else {
                ids.formUnion(expanded)
            }
        }

        return Resolution(
            targetIds: order(ids, by: documents),
            ignoredSelection: ignoredSelection,
            usedRowIdentityFallback: usedFallback
        )
    }

    /// Deterministic order without requiring membership.
    ///
    /// The old code ordered by re-filtering through `documents`, which doubled
    /// as a SECOND presence gate and silently dropped anything the client had
    /// not loaded — so even a target that survived the first check could be
    /// discarded here. Ordering and membership are separate concerns: known
    /// documents keep their visual order, unknown ones sort stably after them
    /// by id. `selection` is a `Set`, so without this the request order would
    /// vary from run to run.
    private static func order(_ ids: Set<String>, by documents: [Document]) -> [String] {
        let indexById = Dictionary(
            documents.enumerated().map { ($1.id, $0) },
            uniquingKeysWith: { first, _ in first }
        )
        return ids.sorted { lhs, rhs in
            let left = indexById[lhs] ?? Int.max
            let right = indexById[rhs] ?? Int.max
            if left != right { return left < right }
            return lhs < rhs
        }
    }

    /// Every descendant FILE of `folderId`, at any depth.
    ///
    /// Breadth-first over a parent→children index, so a box containing archives
    /// containing folders resolves to the files at the bottom — the hierarchy
    /// #4399 depends on. `visited` guards a malformed parent cycle rather than
    /// hanging the menu.
    static func descendantFileIDs(of folderId: String, in documents: [Document]) -> [String] {
        var childrenByParent: [String: [Document]] = [:]
        for document in documents {
            guard let parentId = document.parentId, !parentId.isEmpty else { continue }
            childrenByParent[parentId, default: []].append(document)
        }

        var result: [String] = []
        var queue: [String] = [folderId]
        var visited: Set<String> = [folderId]
        while let next = queue.popLast() {
            for child in childrenByParent[next] ?? [] {
                guard visited.insert(child.id).inserted else { continue }
                if child.docType == .file {
                    result.append(child.id)
                } else {
                    queue.append(child.id)
                }
            }
        }
        return result
    }
}
