import Foundation

/// Does the engine's claim about a search match what actually arrived? (#4505)
///
/// `rendered_total` is the engine's count of every leg it returned. The client
/// knows how many it received. A disagreement is not a display problem — the
/// header is derived from the rendered arrays and stays that way (#4403) — it
/// is a **signal** that something was lost between the two: a leg dropped in
/// transit, a decode failure that discarded hits, a pagination edge.
///
/// Nothing watched for that before. Search would show less than it fetched and
/// look entirely correct doing it, which is the silent-loss shape this codebase
/// keeps finding: a vision fanout returning empty text under a green run, MCP
/// completing successfully having processed zero documents.
///
/// ## Absent is not zero
///
/// `rendered_total` is optional with a default of `0`, so a zero can mean two
/// completely different things and they must not be conflated — the same
/// distinction settled for the confidence badge in #4394, where an unrecorded
/// confidence had been rendering as a real 0.5.
///
///   * **nil** — the field is not on the wire at all. Older engine.
///   * **0 alongside a non-empty body** — the default fired, or an old engine
///     sent a literal zero. The engine did not tell us; that is NOT a claim
///     that nothing was returned, and reporting a mismatch here would cry wolf
///     on every request to an older server.
///   * **0 alongside an empty body** — a genuine, correct agreement: an empty
///     search really did return nothing.
///
/// Only a stated claim is ever compared. Silence is recorded as silence.
enum SearchAgreement: Equatable {
    /// The engine made no claim we can check.
    case notStated
    /// The engine's count and the arrival count match.
    case agrees(count: Int)
    /// They differ — results were lost between the engine and here.
    case disagrees(claimed: Int, arrived: Int)

    /// - Parameters:
    ///   - claimed: `rendered_total` as it came off the wire, `nil` when absent.
    ///   - arrived: legs actually decoded into the response.
    static func resolve(claimed: Int?, arrived: Int) -> SearchAgreement {
        guard let claimed else { return .notStated }
        // The ambiguous zero. Only ambiguous when something DID arrive: a zero
        // over an empty body is a real agreement and is reported as one.
        if claimed == 0, arrived > 0 { return .notStated }
        return claimed == arrived
            ? .agrees(count: arrived)
            : .disagrees(claimed: claimed, arrived: arrived)
    }

    /// The same verdict for a decoded response: the arrival count is every leg
    /// that made it, which is the only thing worth comparing a claim against.
    ///
    /// Lives here rather than in `SearchService` because it IS the rule, and a
    /// rule computed at its call site is a rule that gets computed differently
    /// at the next one.
    static func resolve(for response: SearchResponse) -> SearchAgreement {
        resolve(
            claimed: response.renderedTotal,
            arrived: response.results.count
                + response.entityHits.count
                + response.claimHits.count
                + response.artifactHits.count
        )
    }

    /// True only for a real, checkable disagreement — never for silence, which
    /// is the whole point of the tri-state.
    var isMismatch: Bool {
        if case .disagrees = self { return true }
        return false
    }

    /// What to log. Carries BOTH numbers, because a mismatch report that omits
    /// one of them cannot be acted on.
    var diagnosis: String? {
        guard case let .disagrees(claimed, arrived) = self else { return nil }
        let lost = claimed - arrived
        return lost > 0
            ? "search returned \(arrived) of \(claimed) results the engine reported — \(lost) lost in transit or decode"
            : "search decoded \(arrived) results but the engine reported only \(claimed)"
    }
}
