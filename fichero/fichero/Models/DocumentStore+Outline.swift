import Foundation
import OSLog

// MARK: - The outline consumer seam (Mandate 1, 2026-08-24)
//
// ONE fetch answers "where am I, what's in here" — the crumbs are consumer 1.
// Reads are sync (body-safe) off the cache; hosts kick `loadOutline` from a
// .task keyed on the anchor id. The change stream evicts touched
// neighbourhoods (the approved freshness ruling), so the next read refetches.

extension DocumentStore {
    /// The cached neighbourhood, or nil if never fetched (kick `loadOutline`).
    func outline(for id: String) -> DocumentOutline? {
        outlineCache[id]
    }

    /// Fetch-and-cache. Coalesces trivially: a cached entry returns without a
    /// request, so repeated .task fires on the same anchor cost nothing.
    @discardableResult
    func loadOutline(for id: String) async -> DocumentOutline? {
        if let cached = outlineCache[id] { return cached }
        do {
            let outline = try await documentService.getDocumentView(id)
            outlineCache[id] = outline
            // Nudge observers: the cache is @ObservationIgnored (splice-perf
            // rule), so the crumb hosts re-read via the revision tick.
            revision += 1
            return outline
        } catch {
            logger.error("outline fetch failed for \(id, privacy: .public): \(error.localizedDescription)")
            return nil
        }
    }

    /// Change-stream eviction (the approved v1 freshness rule): a touched
    /// document invalidates its own entry, its parent's (child lists), and
    /// any entry whose ancestors or children mention it.
    func evictOutlines(touching docs: [Document]) {
        guard !outlineCache.isEmpty, !docs.isEmpty else { return }
        let touched = Set(docs.map(\.id))
        let parents = Set(docs.compactMap(\.parentId))
        outlineCache = outlineCache.filter { key, entry in
            if touched.contains(key) || parents.contains(key) { return false }
            if entry.children.contains(where: { touched.contains($0.id) }) { return false }
            if entry.ancestors.contains(where: { touched.contains($0.id) }) { return false }
            return true
        }
    }
}
