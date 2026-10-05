import Foundation

/// A line the teacher-line check flagged (#5446, `source.lines.reading-checked-against-the-page`): the
/// engine's `line-against-page` check run stores a `reject` verdict on each flagged line's reading and
/// lists the line, its flag and its scores in the run (`GET /api/check/runs/{id}`). A line is flagged
/// while the newest verdict on that reading is a reject -- the training set's own rule
/// (`kraken_set.lines_of_pass`) -- so a person's confirm clears it. Pure: the rules live where a test
/// can reach them; `FlaggedLineStore` is the one place that reads the routes.
enum FlaggedLines {
    /// One verdict as `GET /api/check/verdicts` lists it (`CheckVerdict.model_dump(mode="json")`).
    struct Verdict: Decodable, Equatable {
        let id: String
        let targetId: String
        let documentId: String?
        let verdict: String
        let reasons: String
        let trust: String
        let runId: String?
        /// ISO 8601 as the engine writes it; the engine's own order is (created_at, id).
        let createdAt: String

        enum CodingKeys: String, CodingKey {
            case id, verdict, reasons, trust
            case targetId = "target_id"
            case documentId = "document_id"
            case runId = "run_id"
            case createdAt = "created_at"
        }
    }

    struct VerdictList: Decodable {
        let items: [Verdict]
    }

    /// A `line-against-page` run as `GET /api/check/runs/{id}` gives it (`checking/job.status`).
    struct Run: Decodable, Equatable {
        let jobId: String
        let state: String
        /// passed, closer_to_a_neighbour, below_the_threshold, not_scored, checked_by_a_person.
        let counts: [String: Int]
        /// Absent on a check run that is not the teacher-line check (it lists proposals instead).
        let flagged: [Flag]?
        let thresholds: Thresholds?

        enum CodingKeys: String, CodingKey {
            case state, counts, flagged, thresholds
            case jobId = "job_id"
        }

        /// The run is still writing its verdicts: its `flagged` list is not final until it has finished
        /// (the job's states: waiting, running, paused, then done, failed or cancelled).
        var isUnderway: Bool { !["done", "failed", "cancelled"].contains(state) }
    }

    struct Thresholds: Decodable, Equatable {
        /// Below this agreement with its own rough read a line is flagged.
        let low: Double?
    }

    struct Flag: Decodable, Equatable {
        let documentId: String
        let segmentId: String
        let readingId: String
        /// "closer to a neighbour" or "below the threshold".
        let flag: String
        let own: Double
        let neighbour: Double
        /// The neighbour that matched best, in lines from this one (+1 the next line); nil when none.
        let offset: Int?

        enum CodingKeys: String, CodingKey {
            case flag, own, neighbour, offset
            case documentId = "document_id"
            case segmentId = "segment_id"
            case readingId = "reading_id"
        }
    }

    static let closerToANeighbour = "closer to a neighbour"
    static let belowTheThreshold = "below the threshold"

    /// A flagged line as the app shows it.
    struct Line: Equatable {
        let segmentId: String
        /// The reading the check rejected: a person's Confirm is a verdict on THIS reading.
        let readingId: String
        let runId: String
        let flag: String
        let own: Double
        let neighbour: Double
        let offset: Int?
        let low: Double?

        /// The flag as a title: "Closer to a neighbour".
        var title: String { flag.prefix(1).uppercased() + flag.dropFirst() }

        /// The flag and its scores in words (the mark's help, the Inspector's line).
        var words: String {
            if flag == FlaggedLines.closerToANeighbour, let offset {
                return "Teacher text matches \(FlaggedLines.neighbourName(offset)) better "
                    + "(\(FlaggedLines.score(neighbour)) vs \(FlaggedLines.score(own)))"
            }
            if let low {
                return "Teacher text barely matches its own line "
                    + "(\(FlaggedLines.score(own)), below \(FlaggedLines.score(low)))"
            }
            return "Teacher text barely matches its own line (\(FlaggedLines.score(own)))"
        }
    }

    static func score(_ value: Double) -> String { String(format: "%.2f", value) }

    /// "the next line", "the previous line", "the line 2 below", "the line 2 above".
    static func neighbourName(_ offset: Int) -> String {
        switch offset {
        case 1: "the next line"
        case -1: "the previous line"
        default: "the line \(abs(offset)) \(offset > 0 ? "below" : "above")"
        }
    }

    /// A run's counts in words, as the engine says them (`line_check.words`).
    static func countsWords(_ counts: [String: Int]) -> String {
        "\(counts["passed"] ?? 0) passed, \(counts["closer_to_a_neighbour"] ?? 0) closer to a neighbour, "
            + "\(counts["below_the_threshold"] ?? 0) below the threshold"
    }

    /// The runs a page's flags may come from: teacher-line rejects on this page that carry a run.
    static func runIds(_ verdicts: [Verdict], documentId: String) -> [String] {
        var seen: [String] = []
        for verdict in verdicts where verdict.documentId == documentId && verdict.verdict == "reject" {
            if let runId = verdict.runId, !seen.contains(runId) { seen.append(runId) }
        }
        return seen
    }

    /// The page's flagged lines by segment id: each line a run flagged whose reading's NEWEST verdict
    /// is still a reject. A confirm (or a correction) after the reject clears it; a later run that flags
    /// the same line again wins over an earlier one.
    static func flagged(verdicts: [Verdict], runs: [String: Run], documentId: String) -> [String: Line] {
        var newest: [String: Verdict] = [:]
        for verdict in verdicts {
            if let held = newest[verdict.targetId], (held.createdAt, held.id) >= (verdict.createdAt, verdict.id) {
                continue
            }
            newest[verdict.targetId] = verdict
        }
        var lines: [String: Line] = [:]
        for (runId, run) in runs {
            for flag in run.flagged ?? [] where flag.documentId == documentId {
                guard let latest = newest[flag.readingId], latest.verdict == "reject", latest.runId == runId else {
                    continue
                }
                lines[flag.segmentId] = Line(
                    segmentId: flag.segmentId, readingId: flag.readingId, runId: runId, flag: flag.flag,
                    own: flag.own, neighbour: flag.neighbour, offset: flag.offset, low: run.thresholds?.low
                )
            }
        }
        return lines
    }
}
