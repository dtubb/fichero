import Foundation

/// What to do with a refused (stale) note save once the person has chosen (#5348). Pure, so the
/// data-loss cases are testable: the person's text is never dropped without a copy.
enum NoteStaleResolution: Equatable {
    case saveAgainst(Date)
    case copyBecauseDeleted
    case copyAndTakeTheirs

    /// `currentUpdatedAt` is the note's version after a reload; nil when the other Mac deleted it.
    static func decide(keepMine: Bool, currentUpdatedAt: Date?) -> NoteStaleResolution {
        guard keepMine else { return .copyAndTakeTheirs }
        guard let currentUpdatedAt else { return .copyBecauseDeleted }
        return .saveAgainst(currentUpdatedAt)
    }
}
