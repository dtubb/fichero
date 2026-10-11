@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Activity popover after the maintainer's screen of 2026-10-11 (#5666, EAP 1740, a recipe running): a run
/// reads as ONE run with its stages, not as "Transcribe (Kraken) 36 of 91" beside "Transcribe (Kraken) 0 of 91"
/// and "Run the recipe 0 of 1"; only the run in hand's errors show, as a count that opens them; and an error
/// says what happened in words, not a file's path or name.
@MainActor
struct ActivityPopoverRunTests {
    /// A recipe run's tree as `GET /api/activity/jobs/{id}` answers it: three stages, the second running.
    private static func recipeTree() throws -> ActivityJobNode {
        let json = """
        {"id":"r1","kind":"run-a-recipe","name":"Run the recipe","subject":"r1","state":"running","done":36,"total":182,
         "stages":[
           {"steps":["find-lines"],"card":"workflow","state":"done","child_id":"w0",
            "account":{"state":"done","pages_total":91,"pages_done":91}},
           {"steps":["read-a-line"],"card":"workflow","state":"running","child_id":"w1",
            "account":{"state":"running","pages_total":91,"pages_done":36,"waiting_reason":null}},
           {"steps":["keep-an-export"],"card":"export","state":"waiting","child_id":"k1"}],
         "children":[
           {"id":"w0","kind":"workflow","name":"Find lines","display_name":"Find lines","subject":"w0","state":"done",
            "done":91,"total":91},
           {"id":"w1","kind":"workflow","name":"Transcribe (Kraken)","display_name":"Transcribe (Kraken)","subject":"w1",
            "state":"running","done":36,"total":91},
           {"id":"k1","kind":"keep-export","name":"Write a kept export","subject":"k1","state":"waiting","done":0,"total":1}]}
        """
        return ActivityJobNode(try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(json.utf8)))
    }

    private static let jobs: [ActivityJob] = [
        ActivityJob(id: "r1", taskType: "run-a-recipe", name: "Run the recipe", current: 0, total: 1, state: .running),
        ActivityJob(id: "w1", taskType: "workflow", name: "Transcribe (Kraken)", current: 36, total: 91, state: .running),
        ActivityJob(id: "k1", taskType: "keep-export", name: "Write a kept export", current: 0, total: 1, state: .waiting),
        ActivityJob(id: "e-run", taskType: "workflow", name: "Transcribe (Kraken)", state: .failed,
                    reason: "Could not read /Users/ana/EAP 1740/img_0042_Recto.JPG: the image is damaged", runId: "w1"),
        ActivityJob(id: "e-old", taskType: "workflow", name: "Detect Regions", state: .failed,
                    reason: "Kraken not installed")
    ]

    @Test("a recipe run is one run with its stages; its stages are not listed again as jobs")
    func aRunReadsAsOneRun() throws {
        let summary = ActivityPopoverSummary(jobs: Self.jobs, paused: false, runTrees: ["r1": try Self.recipeTree()])
        let run = try #require(summary.runs.first)
        #expect(summary.runs.count == 1)
        // By Set Up's stages (#5670): "Read", not the workflow's "Transcribe (Kraken)"; a step no stage carries, its own.
        #expect(run.stages.map(\.title) == ["Find Lines", "Read", "Write the synced folder"])
        #expect(run.stages.map(\.done) == [91, 36, 0])
        #expect(run.stages.map(\.total) == [91, 91, 0], "a bar per stage, from its own pages")
        #expect(run.stages[1].isRunning && !run.stages[0].isRunning)
        #expect(summary.running.isEmpty, "the run's stages are not listed again beside it")
        #expect(summary.waitingCount == 0, "a waiting stage is the run's, not a waiting job")
    }

    @Test("while a run is in hand, only its errors show, counted; an older one waits in the Activity window")
    func onlyTheRunsErrors() throws {
        let summary = ActivityPopoverSummary(jobs: Self.jobs, paused: false, runTrees: ["r1": try Self.recipeTree()])
        #expect(summary.errorCount == 1)
        #expect(summary.recentErrors.map(\.id) == ["e-run"])
        // The engine's words (its failure is one line per cause, 1bef3cd4d), never rewritten in Swift.
        #expect(summary.recentErrors.first?.fullText
                == "Could not read /Users/ana/EAP 1740/img_0042_Recto.JPG: the image is damaged")
    }

    @Test("with no run in hand, the newest errors show, at most three, and the badge counts them all")
    func noRunNewestErrors() {
        let failed = (1...5).map {
            ActivityJob(id: "f\($0)", taskType: "workflow", name: "Step \($0)", state: .failed, reason: "why \($0)")
        }
        let summary = ActivityPopoverSummary(jobs: failed, paused: false)
        #expect(summary.runs.isEmpty)
        #expect(summary.errorCount == 5)
        #expect(summary.recentErrors.map(\.id) == ["f1", "f2", "f3"])
    }

    @Test("an error says what happened, not where on disk")
    func errorsInWords() {
        let worded = ActivityPopoverSummary.worded
        #expect(worded("Could not read …_Recto.JPG: the image is damaged") == "Could not read a page: the image is damaged")
        #expect(worded("'1933-01-04.jpg' is unreadable") == "a page is unreadable")
        #expect(worded("No such file: /Users/ana/models/kraken/blla.mlmodel") == "No such file: a file")
        #expect(worded("~/Library/Fichero/out.xml could not be written") == "a file could not be written")
        #expect(worded("Kraken not installed") == "Kraken not installed", "words without a path stay as they are")
    }

    // MARK: Daniel, 2026-10-11: one line each, recent only, a bar per running job

    @Test("an error is one line: its job and the cause's first sentence; the whole is its tooltip")
    func errorIsOneLine() throws {
        let job = ActivityJob(id: "e1", taskType: "workflow", name: "Read", state: .failed,
                              reason: "A page could not be read: the image is damaged. 40 pages failed the same way.\nMore")
        let item = try #require(ActivityPopoverSummary(jobs: [job], paused: false).recentErrors.first)
        #expect(item.detail == "A page could not be read: the image is damaged.")
        #expect(ActivityPopoverSummaryView.oneLine(item) == "Read: A page could not be read: the image is damaged.")
        #expect(item.fullText?.contains("40 pages failed the same way") == true, "the whole, for the tooltip")
        #expect(ActivityPopoverSummary.firstSentence("Kraken not installed") == "Kraken not installed")
    }

    @Test("only recent errors: the last hour, or since the popover was last opened, whichever is shorter; at most 3")
    func onlyRecentErrors() {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let window = ActivityErrorWindow(
            seen: ["seen"],
            firstSeen: ["old": now.addingTimeInterval(-2 * 60 * 60), "new": now.addingTimeInterval(-5 * 60),
                        "seen": now.addingTimeInterval(-60)],
            now: now
        )
        #expect(!window.isRecent("old"), "older than an hour")
        #expect(!window.isRecent("seen"), "seen at the last opening, however new")
        #expect(window.isRecent("new") && window.isRecent("never-noted"))
        let jobs = ["old", "seen", "new", "a", "b", "c"].map {
            ActivityJob(id: $0, taskType: "workflow", name: $0, state: .failed, reason: "why")
        }
        let summary = ActivityPopoverSummary(jobs: jobs, paused: false, errorWindow: window)
        #expect(summary.errorCount == 4)
        #expect(summary.recentErrors.map(\.id) == ["new", "a", "b"], "at most three")
    }

    @Test("a closed popover's errors are seen, and do not come back")
    func closedErrorsAreSeen() throws {
        let defaults = try #require(UserDefaults(suiteName: "activity-errors-\(UUID().uuidString)"))
        let ledger = ActivityErrorLedger(defaults: defaults)
        ledger.note(failed: [ActivityJob(id: "e1", name: "Read", state: .failed)])
        #expect(ledger.window().isRecent("e1"))
        ledger.markSeen(["e1"])
        #expect(!ledger.window().isRecent("e1"))
        #expect(!ActivityErrorLedger(defaults: defaults).window().isRecent("e1"), "across launches")
    }

    /// WHY (#5666): the first time this app saw a failure stood in for when it failed, so a failure from yesterday,
    /// first seen at launch, showed as recent. The engine now says when (`failed_at`).
    @Test("a failure is recent by the engine's failed_at; the first sighting stands in only without one")
    func failedAtDecidesRecent() throws {
        let defaults = try #require(UserDefaults(suiteName: "activity-errors-\(UUID().uuidString)"))
        let ledger = ActivityErrorLedger(defaults: defaults)
        let now = Date(timeIntervalSince1970: 2_000_000)
        ledger.note(failed: [
            ActivityJob(id: "yesterday", name: "Read", state: .failed, failedAt: now.addingTimeInterval(-24 * 60 * 60)),
            ActivityJob(id: "just-now", name: "Read", state: .failed, failedAt: now.addingTimeInterval(-60)),
            ActivityJob(id: "no-time", name: "Read", state: .failed)
        ], now: now)
        let window = ledger.window(now: now)
        #expect(!window.isRecent("yesterday"), "first seen now, but it failed a day ago")
        #expect(window.isRecent("just-now"))
        #expect(window.isRecent("no-time"), "without failed_at, the first sighting stands in")
        #expect(ledger.firstSeen["no-time"] == now)

        // Retried and failed again: the new failed_at replaces the old one.
        ledger.note(failed: [ActivityJob(id: "yesterday", name: "Read", state: .failed, failedAt: now)], now: now)
        #expect(ledger.window(now: now).isRecent("yesterday"))
    }

    @Test("the jobs list's failed_at is read into the job")
    func failedAtIsRead() throws {
        let json = #"{"id":"j1","task_type":"workflow","name":"Read","current":0,"total":0,"percent":0,"#
            + #""state":"failed","failed_at":"2026-10-11T18:00:00Z"}"#
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let job = ActivityJob(try decoder.decode(Components.Schemas.BackgroundJob.self, from: Data(json.utf8)))
        #expect(job.failedAt == ISO8601DateFormatter().date(from: "2026-10-11T18:00:00Z"))
    }

    @Test("a running job shows its count on one line over a bar of its own")
    func runningJobHasABar() throws {
        let job = ActivityJob(id: "j1", taskType: "embed", name: "Embedding pages", current: 27, total: 92, state: .running)
        let item = try #require(ActivityPopoverSummary(jobs: [job], paused: false).running.first)
        #expect(item.done == 27 && item.total == 92)
        #expect(ActivityPopoverRunningRow.label(item) == "Embedding pages · 27 of 92")
    }
}
