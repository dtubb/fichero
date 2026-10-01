@testable import Fichero
import FicheroAPIClient
import Testing

/// #5222 part 3: while a library's older results are brought into the page model the window says
/// how far along it is, and when it is done it says so once, with a report. What breaks without
/// these: a line that never goes away (seen is ignored), one that appears for a library that never
/// needed converting, a refusal read as success, or a report that hides the pages that could not go.
@Suite("Conversion notice text (#5222)")
struct ConversionNoticeTextTests {
    @Test("while running: how far along, and that work can go on")
    func running() {
        let status = ConversionSnapshot(running: true, runId: "r1", pagesConverted: 30, pagesSkipped: 2,
                                        pagesNotConverted: [.init(documentId: "d", reason: "x")],
                                        pagesRemaining: 67)
        #expect(ConversionNoticeText.line(status)?.contains("33 of 100 pages") == true)
        #expect(ConversionNoticeText.progress(status) == 0.33)
    }

    @Test("finished and unseen: one line naming what could not be done")
    func finished() {
        let status = ConversionSnapshot(runId: "r1", verdict: "completed", pagesConverted: 93,
                                        pagesNotConverted: [.init(documentId: "doc-7", reason: "a box outside its page")])
        let line = ConversionNoticeText.line(status)
        #expect(line?.contains("93 pages") == true)
        #expect(line?.contains("1 page could not be") == true)
        #expect(ConversionNoticeText.progress(status) == nil)
    }

    @Test("seen, never needed, or nothing to do: nothing is said")
    func silent() {
        #expect(ConversionNoticeText.line(ConversionSnapshot()) == nil)
        #expect(ConversionNoticeText.line(ConversionSnapshot(runId: "r1", verdict: "completed", seen: true)) == nil)
        #expect(ConversionNoticeText.line(ConversionSnapshot(runId: "r1", verdict: "nothing_to_do")) == nil)
    }

    @Test("a refusal is a refusal, with the numbers, and says it will try again")
    func refused() {
        let status = ConversionSnapshot(runId: "r1", verdict: "refused_disk",
                                        diskRequiredBytes: 2_000_000_000, diskAvailableBytes: 500_000_000)
        let line = ConversionNoticeText.line(status) ?? ""
        #expect(line.contains("not brought"))
        #expect(line.contains("try again"))
        #expect(!line.contains("Brought"))
    }

    @Test("the report lists every page that could not be, with its reason, and the snapshot")
    func report() {
        let status = ConversionSnapshot(runId: "r1", verdict: "completed", seconds: 52, pagesConverted: 93,
                                        pagesNotConverted: [.init(documentId: "doc-7", reason: "a box outside its page")],
                                        snapshotPath: "/snapshots/s1",
                                        leftAsTheyWere: [.init(artifactType: "segmentation", count: 4, reason: "no engine producer wrote it")])
        let report = ConversionNoticeText.report(status)
        #expect(report.contains("doc-7: a box outside its page"))
        #expect(report.contains("4 segmentation"))
        #expect(report.contains("/snapshots/s1"))
        #expect(report.contains("52 seconds"))
    }

    @Test("the engine's status maps onto the snapshot the line is worded from")
    func mapsTheEnginesAnswer() {
        let answer = Components.Schemas.ConversionStatus(
            running: false, runId: "r1", verdict: "completed", pagesConverted: 93,
            pagesNotConverted: [.init(documentId: "doc-7", reason: "outside its page")],
            pagesRemaining: 0, seen: false
        )
        let snapshot = ConversionStatusStore.snapshot(answer)
        #expect(snapshot.runId == "r1" && snapshot.verdict == "completed" && snapshot.pagesConverted == 93)
        #expect(snapshot.pagesNotConverted == [.init(documentId: "doc-7", reason: "outside its page")])
        #expect(ConversionNoticeText.line(snapshot) != nil, "an unseen finished run is said once")
    }
}
