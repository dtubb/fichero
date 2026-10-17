import Foundation

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
}
