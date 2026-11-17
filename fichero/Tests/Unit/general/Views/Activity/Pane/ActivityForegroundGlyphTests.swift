@testable import Fichero
import Foundation
import Testing

/// `activity.foreground.one-glyph-not-words` and the app half of `activity.foreground.rank-on-the-row-and-the-pick`
/// (#6442; spec docs/contributor_manual/specs/ui/activity-pane.md): a waiting row whose jobs go next for the page in
/// view carries the eye and no sentence; the status bar counts it in figures; the app reports the page shown, the one
/// before and the five after.
struct ActivityForegroundGlyphTests {
    private func waiting(_ id: String, total: Int, inView: Int = 0) -> ActivityMonitorRow {
        var job = ActivityJob(id: id, taskType: "read-a-page", name: "Read a page", total: total, state: .waiting)
        job.inView = inView
        return ActivityMonitorRow.job(job, libraryId: nil, projectName: nil)
    }

    @Test("the bumped row carries the eye; its words are the tooltip's, and no row text changes")
    func eye() {
        let bumped = waiting("waiting:read", total: 214, inView: 2)
        let other = waiting("waiting:embed", total: 3)
        #expect(ActivityPane.isNextForThePageInView(bumped) && !ActivityPane.isNextForThePageInView(other))
        #expect(ActivityPane.inViewWord == "Next: the page in view")
        #expect(ActivityPane.stateLine(bumped).isEmpty, "no sentence on the row")
        #expect(bumped.name == other.name)
    }

    @Test("the status bar counts it in figures: 2 for the page in view · 215 more; nothing when none is in view")
    func figures() {
        let rows = [waiting("waiting:read", total: 214, inView: 2), waiting("waiting:embed", total: 3)]
        #expect(ActivityPane.inViewFigures(rows) == "2 for the page in view · 215 more")
        #expect(ActivityPane.inViewFigures([waiting("waiting:embed", total: 3)]) == nil)
    }

    @Test("the report is the page shown, then the page before, then the five after")
    func report() {
        let order = (1...30).map { "p\($0)" }
        let items = PageInView.items(shown: "p23", in: order)
        #expect(items.map(\.subject) == ["p23", "p22", "p24", "p25", "p26", "p27", "p28"])
        #expect(items.map(\.rank) == [0, 1, 2, 3, 4, 5, 6])
        #expect(PageInView.items(shown: "p1", in: order).map(\.subject) == ["p1", "p2", "p3", "p4", "p5", "p6"])
        #expect(PageInView.items(shown: "lone", in: order) == [.init(subject: "lone", rank: 0)])
        #expect(PageInView.items(shown: nil, in: order).isEmpty)
    }
}
