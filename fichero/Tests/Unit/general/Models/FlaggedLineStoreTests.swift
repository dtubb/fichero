@testable import Fichero
import Foundation
import Testing

/// A line the teacher-line check flagged shows as flagged (#5446,
/// `source.lines.reading-checked-against-the-page`). Driven through the real `FlaggedLineStore` with the
/// routes' JSON as the engine serves it (`CheckVerdict.model_dump(mode="json")` from
/// `GET /api/check/verdicts`, `checking/job.status` from `GET /api/check/runs/{id}`). What breaks without
/// these: a flagged line that looks like any other (it silently leaves training), a confirmed line still
/// marked (a person's word ignored), or a mark that disagrees with the run's own counts.
@MainActor
struct FlaggedLineStoreTests {
    @MainActor
    final class RecordedTransport: FlaggedLineTransport {
        var verdicts: String
        var runs: [String: String]
        var confirmed: [(readingId: String, segmentId: String)] = []
        var runReads = 0

        init(verdicts: String, runs: [String: String]) {
            self.verdicts = verdicts
            self.runs = runs
        }

        func readingVerdicts(documentId: String) async throws -> Data { Data(verdicts.utf8) }

        func run(id: String) async throws -> Data {
            runReads += 1
            guard let body = runs[id] else { throw SegmentServiceError.unexpectedResponse(404) }
            return Data(body.utf8)
        }

        func confirm(readingId: String, segmentId: String) async throws {
            confirmed.append((readingId, segmentId))
        }
    }

    /// One verdict as `GET /api/check/verdicts` lists it.
    static func verdict(
        _ id: String, reading: String, _ verdict: String, trust: String, run: String?, at time: String,
        document: String = "p1"
    ) -> String {
        """
        {"id": "\(id)", "layer": "readings", "target_id": "\(reading)", "document_id": "\(document)",
         "verdict": "\(verdict)", "reasons": "recorded", "correction": null, "replacement_id": null,
         "checker": "\(trust == "person" ? "owner" : "catmus-print")", "trust": "\(trust)",
         "run_id": \(run.map { "\"\($0)\"" } ?? "null"), "episode_id": null,
         "created_at": "2026-10-05T03:\(time)Z"}
        """
    }

    static func verdictList(_ items: [String]) -> String {
        "{\"items\": [\(items.joined(separator: ", "))], \"count\": \(items.count)}"
    }

    /// The run as `GET /api/check/runs/{id}` gives a finished teacher-line check: 3 passed, line l2
    /// closer to the next line, line l4 below the threshold, and a line on another page.
    static let finishedRun = """
    {"job_id": "run1", "state": "done", "reason": "3 passed, 1 closer to a neighbour, 1 below the threshold",
     "request": {"layer": "readings", "check": "line-against-page", "provider": "kraken", "model": "catmus-print"},
     "counts": {"passed": 3, "closer_to_a_neighbour": 1, "below_the_threshold": 1, "not_scored": 0,
                "checked_by_a_person": 0},
     "flagged": [
       {"document_id": "p1", "segment_id": "l2", "reading_id": "r2", "flag": "closer to a neighbour",
        "own": 0.21, "neighbour": 0.52, "offset": 1},
       {"document_id": "p1", "segment_id": "l4", "reading_id": "r4", "flag": "below the threshold",
        "own": 0.18, "neighbour": 0.12, "offset": -1}
     ],
     "thresholds": {"neighbours": 2, "shift_margin": 0.15, "shift_floor": 0.4, "low": 0.3, "policy": "sergio"},
     "missing": []}
    """

    static let rejects = [
        verdict("v2", reading: "r2", "reject", trust: "model", run: "run1", at: "10:00.000001"),
        verdict("v4", reading: "r4", "reject", trust: "model", run: "run1", at: "10:00.000002")
    ]

    private func loaded(_ verdicts: [String]) async -> (FlaggedLineStore, RecordedTransport) {
        let transport = RecordedTransport(verdicts: Self.verdictList(verdicts), runs: ["run1": Self.finishedRun])
        let store = FlaggedLineStore(transport: transport)
        await store.load(documentId: "p1")
        return (store, transport)
    }

    @Test("a flagged line carries its mark and says its flag and scores in words; a passing line has none")
    func flaggedLineShowsItsWords() async throws {
        let (store, _) = await loaded(Self.rejects)
        let shifted = try #require(store.flag(segmentId: "l2", documentId: "p1"))
        #expect(shifted.title == "Closer to a neighbour")
        #expect(shifted.words == "Teacher text matches the next line better (0.52 vs 0.21)")
        let below = try #require(store.flag(segmentId: "l4", documentId: "p1"))
        #expect(below.words == "Teacher text barely matches its own line (0.18, below 0.30)")
        #expect(store.flag(segmentId: "l1", documentId: "p1") == nil, "a line that passed has no verdict, so no mark")
    }

    @Test("a line a person confirmed after the check is not flagged: the newest verdict on its reading wins")
    func confirmedLineIsNotFlagged() async {
        let confirm = Self.verdict("v5", reading: "r2", "confirm", trust: "person", run: nil, at: "20:00.000000")
        let (store, _) = await loaded(Self.rejects + [confirm])
        #expect(store.flag(segmentId: "l2", documentId: "p1") == nil)
        #expect(store.flag(segmentId: "l4", documentId: "p1") != nil, "a confirm clears only its own line")
    }

    @Test("Confirm sends a person's verdict on the rejected reading and clears that line in place")
    func confirmClearsTheLine() async {
        let (store, transport) = await loaded(Self.rejects)
        await store.confirm(segmentId: "l2", documentId: "p1")
        #expect(transport.confirmed.map(\.readingId) == ["r2"], "the verdict is on the reading the check rejected")
        #expect(transport.confirmed.map(\.segmentId) == ["l2"])
        #expect(store.flag(segmentId: "l2", documentId: "p1") == nil)
        #expect(store.flaggedCount(documentId: "p1") == 1)
        #expect(store.confirmNote == nil)
    }

    @Test("the page's flagged count and the run's words match the run's own counts")
    func countsMatchTheRun() async throws {
        let (store, _) = await loaded(Self.rejects)
        // The run flagged 1 closer to a neighbour + 1 below the threshold, both on this page.
        #expect(store.flaggedCount(documentId: "p1") == 2)
        let line = try #require(store.flag(segmentId: "l2", documentId: "p1"))
        #expect(store.runWords(line) == "3 passed, 1 closer to a neighbour, 1 below the threshold")
    }

    @Test("a reject on another page is not counted or shown on this one")
    func onlyThisPagesCurrentFlags() async {
        let otherPage = Self.verdict("v9", reading: "r9", "reject", trust: "model", run: "run1", at: "10:00.000003", document: "p2")
        let (store, _) = await loaded(Self.rejects + [otherPage])
        #expect(store.flaggedCount(documentId: "p1") == 2)
        #expect(store.flag(segmentId: "l9", documentId: "p1") == nil)
    }

    @Test("a run still underway shows nothing yet, and is not kept as if finished")
    func runUnderwayShowsNothing() async {
        let running = Self.finishedRun.replacingOccurrences(of: "\"state\": \"done\"", with: "\"state\": \"running\"")
        let transport = RecordedTransport(verdicts: Self.verdictList(Self.rejects), runs: ["run1": running])
        let store = FlaggedLineStore(transport: transport)
        store.settle = .seconds(600)
        await store.load(documentId: "p1")
        #expect(store.runs["run1"] == nil)
        #expect(store.flaggedCount(documentId: "p1") == 0)
    }

    @Test("the neighbour is named by where it is: next, previous, or n lines below or above")
    func neighbourNames() {
        #expect(FlaggedLines.neighbourName(1) == "the next line")
        #expect(FlaggedLines.neighbourName(-1) == "the previous line")
        #expect(FlaggedLines.neighbourName(2) == "the line 2 below")
        #expect(FlaggedLines.neighbourName(-2) == "the line 2 above")
    }
}
