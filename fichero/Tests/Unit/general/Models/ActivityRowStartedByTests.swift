@testable import Fichero
import Foundation
import Testing

/// `sharing.sync.remote-run-live-in-activity` (#5732): a run another Mac's person started names them in the list; the
/// host's own and automatic runs name no one there.
@MainActor
struct ActivityRowStartedByTests {
    private func row(startedBy: String?) -> ActivityMonitorRow {
        var row = ActivityMonitorRow(
            id: "r", kind: .run, libraryId: nil, runRowID: nil, runThreadId: nil, jobId: "j", name: "Read", projectName: nil,
            phase: .running, reason: nil, workingOn: nil, done: 0, total: 0, started: nil, seconds: nil, costUsd: nil,
            tokens: 0, errors: 0, model: nil, isLive: true, children: nil, account: nil
        )
        row.startedBy = startedBy
        return row
    }

    @Test func aPersonOnADeviceIsNamed() {
        #expect(row(startedBy: "maya on Maya's Mac").remoteStarter == "Started by maya on Maya's Mac")
        #expect(row(startedBy: "Claude Code for maya").remoteStarter == "Started by Claude Code for maya")
    }

    @Test func theHostsOwnAndAutomaticRunsNameNoOne() {
        for raw in [nil, "owner", "automatic", "schedule:nightly", "workflow"] {
            #expect(row(startedBy: raw).remoteStarter == nil, "\(raw ?? "nil")")
        }
    }
}
