import Foundation

extension String {
    /// Finder's name order (owner 2026-11-13, spec `library.sort.names-in-finder-order`):
    /// case-insensitive, accents per the locale, numbers compared by value
    /// (1, 2, ... 9, 10, 11, ... 100, never 1, 10, 100, 2). Names that compare equal that way
    /// fall back to the exact characters, so the order is stable. The ONE comparison every
    /// name-ordered list uses, with the engine's `natural_key` on the other side.
    nonisolated func finderOrder(_ other: String) -> Bool {
        switch localizedStandardCompare(other) {
        case .orderedAscending: return true
        case .orderedDescending: return false
        case .orderedSame: return self < other
        }
    }
}
