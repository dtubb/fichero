@testable import Fichero
import Foundation
import Testing

/// VoiceOver hears work start, finish and fail (#3724, `activity.voiceover-announcements`), from the jobs read the
/// Activity surfaces already use: at the transitions only, never a tick, and never what was running before the app
/// looked.
@MainActor
struct ActivityAnnouncementTests {
    private func job(_ id: String, _ state: ActivityJob.State, name: String = "Import 12 files",
                     reason: String? = nil, parent: String? = nil, current: Int = 0) -> ActivityJob {
        ActivityJob(id: id, name: name, current: current, state: state, reason: reason, parentId: parent)
    }

    /// WHY: a blind user got silence, then had to go hunting to find out whether the import finished or failed.
    @Test("started, finished and failed are said; a failure says why")
    func transitionsAreSaid() {
        #expect(ActivityStore.announcement(from: [], to: [job("a", .running)]) == "Import 12 files started")
        #expect(ActivityStore.announcement(from: [job("a", .running)], to: []) == "Import 12 files finished",
                "a finished job leaves the list")
        #expect(ActivityStore.announcement(from: [job("a", .running)], to: [job("a", .completed)]) == "Import 12 files finished")
        #expect(ActivityStore.announcement(from: [job("a", .running)], to: [job("a", .failed, reason: "Kraken not installed")])
                == "Import 12 files failed: Kraken not installed")
    }

    /// WHY: an announcement on every progress tick, or for every page of a run, is chatter nobody can use.
    @Test("progress, a page's step and what was already running when the app looked say nothing")
    func noChatter() {
        #expect(ActivityStore.announcement(from: [job("a", .running, current: 1)], to: [job("a", .running, current: 2)]) == nil)
        #expect(ActivityStore.announcement(from: [], to: [job("p1", .running, parent: "run")]) == nil)
        #expect(ActivityStore.announcement(from: nil, to: [job("a", .running)]) == nil, "the first read is not news")
        #expect(ActivityStore.announcement(from: [job("a", .failed)], to: [job("a", .failed)]) == nil, "said once")
    }

    @Test("several changes in one read are one announcement")
    func oneAnnouncementPerRead() {
        let said = ActivityStore.announcement(
            from: [job("a", .running)],
            to: [job("a", .failed, reason: nil), job("b", .running, name: "Read 40 pages")]
        )
        #expect(said == "Import 12 files failed. Read 40 pages started")
    }
}
