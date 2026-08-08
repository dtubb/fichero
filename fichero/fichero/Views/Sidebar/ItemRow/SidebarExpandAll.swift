import SwiftUI

// Option-click expand-all: the descend predicate and the concurrent
// level-order walk. Split from SidebarItemRow.swift for the file-length
// budget (Daniel, 2026-08-08); the row's isExpanded binding calls
// sidebarExpandSubtree. See each doc comment for the three task-group
// shapes the Swift 6 region checker rejected on the way here.

/// Which children an option-click expand-all descends into: any container
/// that HAS children — folders, and page-bearing documents like PDFs (their
/// page rows are already in the database; `childCount` is honest since
/// #4515). A folder whose count hasn't arrived yet is still descended so a
/// stale zero can't silently prune a subtree.
func sidebarSubtreeShouldDescend(into child: Document) -> Bool {
    child.docType == .folder || child.childCount > 0
}

/// Option-click expands the ENTIRE subtree (Finder), lazily loading each
/// level. An explicit user gesture, so the deep fan-out fetch is acceptable
/// — unlike the bounded one-level prefetch in `loadSidebarChildren`.
///
/// Sibling subtrees fetch CONCURRENTLY: the serial version awaited one
/// network round trip per container, so option-expanding K containers took
/// K × RTT and PDFs visibly lagged their pages (Daniel, 2026-08-08) even
/// though every page row already sits in DuckDB. URLSession's per-host
/// connection pool bounds the actual fan-out.
///
/// A free function, not a `SidebarItemRow` method: the child tasks must not
/// capture the row struct (non-Sendable stored services trip the compiler's
/// region-based isolation checker). The walk itself lives in
/// `sidebarSubtreeExpansionIDs`, which RETURNS the ids rather than writing
/// them — see its doc comment for why the Binding must not travel into the
/// recursion.
@MainActor
func sidebarExpandSubtree(
    _ document: Document,
    store: DocumentStore,
    expandedItems: Binding<Set<String>>
) async {
    expandedItems.wrappedValue.formUnion(
        await sidebarSubtreeExpansionIDs(document, store: store)
    )
}

/// The ids to expand for `document` and every descendant worth descending
/// into — the concurrent walk, RETURNING its result.
///
/// The Binding deliberately does NOT travel into the recursion: `Binding`
/// wraps get/set closures, so a Sendable `Value` does not make the Binding
/// itself Sendable, and capturing one in a task-group child is a hard ERROR
/// under Swift 6 ("pattern the region-based isolation checker does not
/// understand how to check" — the diagnostic five commits stacked on).
/// Every capture here is Sendable-safe: a `@unchecked Sendable` Document
/// and the MainActor-bound store, inside a `@MainActor` child closure.
@MainActor
private func sidebarSubtreeExpansionIDs(
    _ document: Document,
    store: DocumentStore
) async -> Set<String> {
    // LEVEL-ORDER with UNSTRUCTURED tasks, after two rejected shapes: the
    // region checker errors on any `group.addTask` capturing the MainActor
    // store — recursive (build 09:22) and plain (build 09:24) alike. A
    // `Task {}` created here inherits MainActor, so capturing the store is
    // the same legal pattern the option-click call site already compiles
    // (`Task { await store.loadSidebarChildren(of:) }`). All of a level's
    // tasks start before any is awaited, so their network awaits interleave:
    // wall clock is depth × RTT, not nodes × RTT. Unstructured means no
    // automatic cancellation propagation — fine for an explicit user gesture
    // whose store calls are themselves cancellation-tolerant.
    var frontier = [document]
    var ids: Set<String> = []
    while !frontier.isEmpty {
        ids.formUnion(frontier.map { "doc:\($0.id)" })
        let levelFetches = frontier.map { node in
            Task { await store.cacheSidebarChildren(of: node) }
        }
        var nextLevel: [Document] = []
        for fetch in levelFetches {
            nextLevel.append(
                contentsOf: await fetch.value.filter { sidebarSubtreeShouldDescend(into: $0) }
            )
        }
        frontier = nextLevel
    }
    return ids
}
