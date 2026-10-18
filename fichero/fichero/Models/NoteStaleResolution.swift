import Foundation

/// The two texts shown side by side when the person picks Compare (#5348).
struct NoteStaleComparison: Equatable, Identifiable {
    var id: String { mine + "\u{0}" + theirs }
    let mine: String
    let theirs: String
}

/// What to do with a refused (stale) note save once the person has chosen (#5348). Pure, so the
/// cases are testable. A shared library is shared editing (owner ruling 2026-10-17): a note deleted on
/// another Mac is deleted here, so there is nothing to keep, resurrect or copy.
enum NoteStaleResolution: Equatable {
    case saveAgainst(Date)
    case deletedElsewhere
    case copyAndTakeTheirs

    /// `currentUpdatedAt` is the note's version after a reload; nil when the other Mac deleted it.
    static func decide(keepMine: Bool, currentUpdatedAt: Date?) -> NoteStaleResolution {
        guard keepMine else { return .copyAndTakeTheirs }
        guard let currentUpdatedAt else { return .deletedElsewhere }
        return .saveAgainst(currentUpdatedAt)
    }

    /// Compare shows my dropped text beside the other Mac's; nil when it was deleted there (nothing to compare).
    static func comparison(mine: String, theirs: String?) -> NoteStaleComparison? {
        theirs.map { NoteStaleComparison(mine: mine, theirs: $0) }
    }
}
