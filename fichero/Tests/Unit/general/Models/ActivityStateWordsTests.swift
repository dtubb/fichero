//
//  ActivityStateWordsTests.swift
//  FicheroTests
//
//  #5957, #5958: every state the engine reports has its own words, an unknown one says so (never Done), and a waiting run reads
//  waiting. Specs: `activity.window.every-state-has-its-words`, `activity.window.waiting-run-reads-waiting`.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ActivityStateWordsTests {
    typealias Phase = ActivityMonitorRow.Phase

    private func row(_ phase: Phase, reason: String? = nil, unknown: String? = nil) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: "r", kind: .run, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: "j", name: "Run", projectName: nil,
            phase: phase, reason: reason, workingOn: nil, done: 0, total: 0, started: nil, seconds: nil, costUsd: nil,
            tokens: 0, errors: 0, model: nil, isLive: false, children: nil, account: nil, unknownState: unknown
        )
    }

    @Test("each engine state maps to its own phase and words")
    func eachStateHasItsWords() {
        let expected: [(String, Phase, String)] = [
            ("running", .running, "Running"), ("waiting", .waiting, "Waiting"), ("accepted", .waiting, "Waiting"),
            ("queued", .waiting, "Waiting"), ("paused", .paused, "Paused"), ("failed", .failed, "Failed"),
            ("cancelled", .cancelled, "Stopped"), ("done", .done, "Done"), ("completed", .done, "Done"),
            ("partial", .partial, "Partial"), ("interrupted", .interrupted, "Interrupted"), ("not run", .notRun, "Not run"),
        ]
        for (state, phase, words) in expected {
            #expect(Phase(engineState: state) == phase, "\(state)")
            #expect(row(phase).stateText == words, "\(state)")
        }
    }

    @Test("a state nobody knows is unknown and says its name, never Done")
    func unknownIsNeverDone() {
        let phase = Phase(engineState: "quarantined")
        #expect(phase == .unknown && phase != .done)
        #expect(row(phase, unknown: "quarantined").stateText == "unknown state quarantined")
        #expect(ActivityMonitorRow.Phase(ActivityJob.State.other("held")) == .unknown)
        #expect(ActivityJob.State.other("held").otherName == "held")
    }

    @Test("partial, interrupted and not-run rows say why in the engine's words")
    func reasonsShow() {
        #expect(row(.partial, reason: "2 of 5 pages done").stateText == "Partial: 2 of 5 pages done")
        #expect(row(.interrupted, reason: "Interrupted: the engine stopped").stateText == "Interrupted: the engine stopped")
    }

    @Test("a node in a state the app does not know is its own bucket, not running; transient states stay live")
    func unknownIsItsOwnBucket() throws {
        let run = ActivityRun(node: try jobNode(state: "quarantined"), libraryId: nil, libraryName: nil)
        #expect(run.status == .unknown && run.status != .running)
        #expect(ActivityMonitorRow.run(run, tree: nil).stateText == "unknown state quarantined")
        for transient in ["stopping", "pausing", "resuming", "retrying"] {
            #expect(Phase(engineState: transient) == .running, "\(transient)")
        }
    }

    @Test("a run the engine says is waiting is drawn waiting, not Running")
    func waitingRunReadsWaiting() throws {
        let node = ActivityRun(node: try jobNode(state: "waiting"), libraryId: nil, libraryName: nil)
        #expect(node.engineState == "waiting")
        let built = ActivityMonitorRow.run(node, tree: nil)
        #expect(built.phase == .waiting && built.looksWaiting)
        #expect(!built.isLive)
    }

    @Test("a run part-way through Stop, Pause, Resume or Retry says so, not Running (## 697)")
    func transientStatesHaveTheirOwnWords() throws {
        let words = ["stopping": "Stopping", "pausing": "Pausing", "resuming": "Resuming", "retrying": "Retrying"]
        for (state, word) in words {
            let run = ActivityRun(node: try jobNode(state: state), libraryId: nil, libraryName: nil)
            let row = ActivityMonitorRow.run(run, tree: nil)
            #expect(row.phase == .running && row.stateText == word, "\(state)")
        }
        let plain = ActivityRun(node: try jobNode(state: "running"), libraryId: nil, libraryName: nil)
        #expect(ActivityMonitorRow.run(plain, tree: nil).stateText == "Running")
    }

    private func jobNode(state: String) throws -> ActivityJobNode {
        let json = """
        {"id":"run-1","kind":"workflow","name":"Transcribe","subject":"run-1","state":"\(state)","done":0,"total":0}
        """
        return ActivityJobNode(try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(json.utf8)))
    }
}
