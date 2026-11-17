@testable import Fichero
import Foundation
import Testing

/// `activity.resources.everything-measured` (#6588, decision 42; spec
/// docs/contributor_manual/specs/ui/activity-pane.md): a cluster read's time queued and time run, this Mac's memory,
/// processor and lanes; what nothing measures reads "—".
struct ActivityResourcesMeasuredTests {
    private func run(queued: Double?, ran: Double?, nodeHours: Double? = nil,
                     cost: Double? = nil) -> RemoteRunService.Run {
        RemoteRunService.Run(target: "acenet", farState: "running", shardsDone: 1, shardsTotal: 2, pagesLanded: 10,
                             shards: [], estimateGpuHours: nil, actualSecondsPerShard: nil, queuedSeconds: queued,
                             runSeconds: ran, nodeHours: nodeHours, costUsd: cost)
    }

    @Test("a cluster job of 40 min queued and 12 min run reads both; nothing measured, no line")
    func clusterTimes() {
        let words = run(queued: 2400, ran: 720, nodeHours: 0.2).timesWords
        #expect(words?.contains("40") == true && words?.contains("12") == true)
        #expect(words?.contains("queued") == true && words?.contains("node-hours") == true)
        #expect(words?.contains("$") == false, "no price: no cost made up")
        #expect(run(queued: nil, ran: nil).timesWords == nil)
    }

    @Test("this Mac reads memory used of its total and its load; unmeasured is a dash")
    func thisMac() {
        let lanes: [ActivityThisMac.Lane] = [
            .init(lane: "network", busy: 2, width: 4), .init(lane: "embed", busy: 0, width: 1),
        ]
        let mac = ActivityThisMac(memoryUsedBytes: 12 << 30, memoryTotalBytes: 16 << 30, processorPercent: 24.6,
                                  lanes: lanes)
        #expect(mac.words.hasSuffix(" · 25%") && mac.words.contains(" of "))
        #expect(mac.lanesWords == "network 2 of 4")
        #expect(ActivityThisMac().words == "— · —")
        #expect(ActivityThisMac().lanesWords == "No lane busy")
    }

    @Test("two projects' answers: the Mac once, each lane's work added")
    func merged() {
        let one = ActivityThisMac(memoryTotalBytes: 1, lanes: [.init(lane: "network", busy: 1, width: 4)])
        let two = ActivityThisMac(memoryTotalBytes: 1, lanes: [.init(lane: "network", busy: 2, width: 4),
                                                              .init(lane: "local-ml", busy: 1, width: 1)])
        let total = ActivityThisMac.merged([one, two])
        #expect(total?.lanes.map(\.busy) == [3, 1])
        #expect(ActivityThisMac.merged([]) == nil)
    }
}
