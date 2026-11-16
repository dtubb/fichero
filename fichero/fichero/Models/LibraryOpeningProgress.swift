import Foundation

/// #6430: while several libraries open at launch (the engine opens at most two at a time), the pane of one that is still
/// waiting says which it is and where it stands, instead of a bare spinner.
enum LibraryOpeningProgress {
    /// "Opening Marshall (2 of 4)…"; nil when only one library is open (nothing to count), this one is not in the order, or
    /// it has already loaded (a later refetch is not an opening).
    static func message(name: String, id: UUID, order: [UUID], loaded: Set<UUID> = []) -> String? {
        guard order.count > 1, !loaded.contains(id), let index = order.firstIndex(of: id) else { return nil }
        return "Opening \(name) (\(index + 1) of \(order.count))…"
    }
}
