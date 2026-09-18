import Foundation

/// Pure entity-name heuristics, extracted from `OntologyBrowser` (#4705
/// increment 3) so they survive the KG sidebar mode's retirement — unlike
/// `OntologyBrowser`'s other filter helpers (`parseHiddenKinds`,
/// `filterEntities`, `isDateEntity`), `isOcrGarbage` has a real caller
/// outside the browser (`LibraryView+FilterAndBatch.swift`), which is what
/// earns it this neutral home instead of dying with the rest of the file.
enum EntityNameHeuristics {
    /// Returns true if `name` looks like OCR noise rather than a meaningful
    /// entity name. Heuristics: single character, all-numeric, or fewer than
    /// half the characters are letters (#1168).
    static func isOcrGarbage(_ name: String) -> Bool {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        guard trimmedName.count >= 2 else { return true }
        if trimmedName.allSatisfy({ !$0.isLetter }) { return true }
        let letterRatio = Double(trimmedName.filter(\.isLetter).count) / Double(trimmedName.count)
        return letterRatio < 0.5
    }
}
