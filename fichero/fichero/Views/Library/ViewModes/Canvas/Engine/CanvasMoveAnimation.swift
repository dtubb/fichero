import Foundation

// MARK: - How long a card takes to reach its new slot (R10, §20.2)

/// The duration of a `.move`, shared by both renderers.
///
/// R10's rule is "the cards move, the camera cuts, the user never flies", and
/// §20.2 argues the re-arrangement itself is the information: switching
/// arrangements and watching 2,228 page images fly tells you which cards did
/// NOT move (the ones you pinned) and where the record breaks. That only reads
/// if the motion is long enough to follow.
///
/// But one card echoing in from another window is not a transition — it is
/// feedback, and feedback wants to be quick. So duration scales with how many
/// cards the diff moved at once, between two fixed ends:
///
/// - **one or a few cards** — 0.18s, the value the 2D renderer already shipped
///   for cross-window and agent moves.
/// - **a whole board** — 0.55s, inside §20.2's "600 milliseconds" band.
///
/// The top end is capped hard. Every Frame Perfect cuts both ways: a board that
/// floats for a second reads as broken rather than elegant, and a re-arrange
/// the user is waiting on has stopped being information.
enum CanvasMoveAnimation {
    /// A single card responding to something that happened elsewhere.
    static let feedbackDuration = 0.18
    /// A whole-board re-arrange. Hard ceiling — nothing returns more than this.
    static let transitionDuration = 0.55
    /// Above this many cards in one diff, it is a re-arrange rather than an
    /// echo. Deliberately low: a handful of cards moving together is already a
    /// transition worth watching, and the cost of being wrong in this direction
    /// is a slightly slower echo, not a wrong picture.
    static let transitionThreshold = 8

    /// Seconds every `.move` in this diff animates for. Both renderers call
    /// this once per `apply`, so they cannot disagree about how a re-arrange
    /// feels.
    static func duration(for ops: [CanvasSceneOp]) -> Double {
        duration(movedCount: ops.reduce(into: 0) { count, operation in
            if case .move = operation { count += 1 }
        })
    }

    /// Seconds for a `.move`, given how many cards this diff moves.
    ///
    /// Between the two ends it eases in linearly rather than jumping, so a
    /// 20-card folder does not animate at a visibly different speed from a
    /// 30-card one.
    static func duration(movedCount: Int) -> Double {
        guard movedCount > 1 else { return feedbackDuration }
        guard movedCount < transitionThreshold else { return transitionDuration }
        let progress = Double(movedCount - 1) / Double(transitionThreshold - 1)
        return feedbackDuration + (transitionDuration - feedbackDuration) * progress
    }
}
