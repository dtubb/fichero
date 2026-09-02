import SwiftUI

// MARK: - Selection-scoped stepping (split from +ActionsNavigation for
// file_length): the three walks that rotate WITHIN a selection — sidebar,
// library, and the nil-detail seeding that lets a fan rotate at all.

extension ContentView {
    /// Sidebar-scoped stepping (Daniel, 2026-08-21): with MULTIPLE sidebar
    /// rows selected, ←/→ rotates within that selection (wrap-around); the
    /// walk works whether or not the library pane has focus, because it rides
    /// the same notification the swipe posts. Returns true when it consumed
    /// the step.
    func stepWithinSidebarSelection(forward: Bool, from current: Document) -> Bool {
        let selectedDocIds = sidebarSelectionState.selectedDestinations.compactMap { dest -> String? in
            if case .document(let id) = dest { return id }
            return nil
        }
        guard selectedDocIds.count > 1, selectedDocIds.contains(current.id) else { return false }
        let pool = documentStore.currentDocuments
            + documentStore.collections
            + documentStore.childrenCache.values.flatMap { $0 }
        var docsById: [String: Document] = [:]
        for doc in pool where docsById[doc.id] == nil { docsById[doc.id] = doc }
        let members = displayOrdered(
            selectedDocIds.compactMap { docsById[$0] },
            folderId: current.parentId
        )
        guard members.count > 1,
              let idx = members.firstIndex(where: { $0.id == current.id }) else { return false }
        let target = members[(idx + (forward ? 1 : members.count - 1)) % members.count]
        NavTrace.log("stepWithinSidebarSelection", "\(current.id) → \(target.id)")
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
        return true
    }

    /// Library-selection rotation (Daniel, 2026-08-23: "have three cards
    /// selected, preview should let us rotate just between them"): with
    /// MULTIPLE library cards selected, ←/→ cycles detailDocument through the
    /// selection (wrap-around) and NEVER collapses it — the fan's front card
    /// follows. Symmetric to stepWithinSidebarSelection, one pane over.
    func stepWithinLibrarySelection(forward: Bool, from current: Document) -> Bool {
        guard browserSelection.count > 1, browserSelection.contains(current.id) else { return false }
        let pool = documentStore.currentDocuments
            + documentStore.childrenCache.values.flatMap { $0 }
        var docsById: [String: Document] = [:]
        for doc in pool where docsById[doc.id] == nil { docsById[doc.id] = doc }
        let members = displayOrdered(
            browserSelection.compactMap { docsById[$0] },
            folderId: current.parentId
        )
        guard members.count > 1,
              let idx = members.firstIndex(where: { $0.id == current.id }) else { return false }
        let target = members[(idx + (forward ? 1 : members.count - 1)) % members.count]
        NavTrace.log("stepWithinLibrarySelection", "\(current.id) → \(target.id)")
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            // browserSelection stays intact — rotation happens WITHIN it.
        }
        return true
    }

    /// Search-results stepping (Daniel, 2026-09-02: "swipe left right in
    /// library search, to move between search results"): while the library
    /// shows SEARCH RESULTS, ←/→ and the sibling swipe walk the RESULTS in
    /// relevance order — not the folder the current hit happens to live in.
    /// Deliberately NOT displayOrdered: relevance IS the results' order, and
    /// re-sorting it by a folder's saved sort would walk a different list
    /// than the one on screen (the visible-surface ruling). No wrap: the ends
    /// are the ends, same as folder stepping. Returns true when it consumed
    /// the step.
    func stepWithinSearchResults(forward: Bool, from current: Document) -> Bool {
        guard activeSearchQuery != nil, searchResultDocuments.count > 1,
              let idx = searchResultDocuments.firstIndex(where: { $0.id == current.id })
        else { return false }
        let next = idx + (forward ? 1 : -1)
        guard searchResultDocuments.indices.contains(next) else { return true }
        let target = searchResultDocuments[next]
        NavTrace.log("stepWithinSearchResults", "\(current.id) → \(target.id)")
        withAnimation(.easeInOut(duration: 0.2)) {
            detailDocument = target
            browserSelection = [target.id]
        }
        return true
    }

}
