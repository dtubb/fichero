//
//  ActivityTextBudgetTests.swift — `activity.pane.text-budget`, `activity.pane.error-row-shape` (#6441): every cell's words
//  within eight and no sentence; pages failing for one reason say it once with their count.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityTextBudgetTests {
    typealias Fixture = ActivityPaneFixture

    private func every(_ rows: [ActivityMonitorRow]) -> [ActivityMonitorRow] {
        rows.flatMap { [$0] + every($0.children ?? []) }
    }

    private func failedRun(pages: Int, reason: (Int) -> String) -> ActivityMonitorRow {
        let children = (0..<pages).map { index in
            var page = Fixture.page("p\(index)", .failed, doc: "d\(index)")
            page.reason = reason(index)
            return page
        }
        return Fixture.row("run", .failed, kind: .run, name: "Letters", children: children)
    }

    @Test("every row of the fixture, by Run and by File, keeps each cell within eight words and holds no full stop")
    func withinTheBudget() {
        let runs = [Fixture.letters, Fixture.names, failedRun(pages: 12) { _ in "No credit left." }]
        for row in every(ActivityPane.outline(runs) + ActivityPane.byFile(runs)) {
            for cell in ActivityPane.cellWords(row) {
                #expect(ActivityPane.words(cell) <= ActivityPane.wordBudget, "\(row.id): \(cell)")
                #expect(!cell.hasSuffix("."), "\(row.id): \(cell)")
            }
        }
    }

    @Test("twelve pages failing for one reason: one line with the count; different reasons: no line on the run")
    func collapsedBySameReason() {
        #expect(ActivityPane.stateLine(failedRun(pages: 12) { _ in "No credit left." }) == "No credit left · 12 pages")
        #expect(ActivityPane.stateLine(failedRun(pages: 2) { "Reason \($0)" }) == "")
        #expect(ActivityPane.stateLine(failedRun(pages: 1) { _ in "No credit left." }) == "No credit left")
    }

    @Test("a reason longer than the budget is never cut: the row says nothing and the Inspector has the sentence")
    func neverCut() {
        var row = Fixture.row("job", .failed, name: "Read")
        row.reason = "The provider refused the request because the account has no credit left at all."
        #expect(ActivityPane.stateLine(row) == "")
    }
}
