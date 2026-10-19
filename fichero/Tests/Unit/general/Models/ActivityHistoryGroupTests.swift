//
//  ActivityHistoryGroupTests.swift
//  FicheroTests
//
//  #5851 (owner, 2026-10-19): finished, stopped and interrupted runs fold into History; the live area holds only the
//  live run and the queues beside it. The engine ranks every row and marks the ended ones `group: "earlier"`;
//  the store splits its one jobs read on that. Spec: `activity.window.history-group`.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct ActivityHistoryGroupTests {
    private func makeStore() -> ActivityStore {
        let client = FicheroClient(libraryPath: "/tmp/test.fichero")
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    @Test func theStoreSplitsTheJobsReadIntoLiveAndHistory() {
        let store = makeStore()
        store.backgroundJobs = [
            ActivityJob(id: "live", taskType: "workflow", name: "Transcribe", state: .running),
            ActivityJob(id: "queue", taskType: "embed", name: "Embed for search", state: .waiting),
            ActivityJob(id: "stopped", taskType: "run-a-recipe", name: "Run the recipe", state: .failed, isEarlier: true),
            ActivityJob(id: "old", taskType: "workflow", name: "Earlier run", state: .failed, isEarlier: true),
        ]
        #expect(store.liveJobs.map(\.id) == ["live", "queue"])
        #expect(store.historyJobs.map(\.id) == ["stopped", "old"])
    }

    @Test func aRowIsLiveUnlessTheEngineSaidEarlier() {
        #expect(ActivityJob(id: "a", name: "A").isEarlier == false)
    }
}
