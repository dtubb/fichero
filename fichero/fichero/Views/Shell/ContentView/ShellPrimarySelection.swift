import Foundation

/// The ONE answer to "which selected row is primary" at the shell boundary
/// (2026-08-09, the selection-identity contract): first match in the given
/// DOCUMENT ORDER — the order the user sees — falling back to the stable
/// lexical minimum for ids not in the loaded list (restore-before-load).
/// Never `Set.first`: hash order made the promoted preview, the entity
/// focus, and the stale-fetch guard each capable of drawing a DIFFERENT
/// element from the same multi-selection.
func shellPrimarySelectionId(in selection: Set<String>, orderedBy documents: [Document]) -> String? {
    guard !selection.isEmpty else { return nil }
    if let inOrder = documents.first(where: { selection.contains($0.id) }) {
        return inOrder.id
    }
    return selection.min()
}
