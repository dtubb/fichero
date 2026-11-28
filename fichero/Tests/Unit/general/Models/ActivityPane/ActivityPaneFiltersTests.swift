//
//  ActivityPaneFiltersTests.swift — `activity.pane.history-kept-and-filterable` (#6441): `key: value` tokens ANDed over
//  both groupings, remembered per pane; history stays in the same table.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneFiltersTests {
    typealias Fix = ActivityPaneFixture

    @Test("the grammar: keys, plain text, an unknown key as text, an empty value dropped")
    func grammar() {
        let filter = ActivityPaneFilter("model: Kraken state: failed letters size: big step:")
        // A key's value runs to the next key; "size:" is no key, so it is part of the value; "step:" has none and is dropped.
        #expect(filter.tokens == [
            .init(key: .model, value: "Kraken"), .init(key: .state, value: "failed letters size: big")
        ])
        #expect(ActivityPaneFilter("started by: automatic").tokens == [.init(key: .startedBy, value: "automatic")])
        #expect(ActivityPaneFilter("letters").tokens == [.init(key: nil, value: "letters")])
        #expect(ActivityPaneFilter("  ").isEmpty)
    }

    @Test("model: Kraken with state: failed keeps the one failed Kraken read and the way to it; clearing shows everything")
    func krakenFailed() throws {
        let rows = ActivityPane.byFile([Fix.letters])
        let kept = ActivityPaneFilter("model: Kraken state: failed").apply(rows)
        #expect(kept.map(\.documentId) == ["p2"])
        #expect(kept.first?.children?.map(\.name) == ["Letters › Read"])
        #expect(ActivityPaneFilter("").apply(rows) == rows)
    }

    /// `activity.pane.automatic-runs-easy-to-delete` (#6583): the token, then ⌘A and Delete over what it leaves.
    @Test("started by: automatic keeps the import's, the schedule's, a trigger's and the derivative rows, and no row a person started")
    func startedByAutomatic() {
        func started(_ id: String, by starter: String?, kind: ActivityMonitorRow.Kind = .job) -> ActivityMonitorRow {
            var row = Fix.row(id, .done, kind: kind)
            row.startedBy = starter
            return row
        }
        let thumbnails = (1...40).map { started("thumb-\($0)", by: "derivatives") }
        let automatic = thumbnails + [
            started("import-run", by: "import", kind: .run), started("nightly", by: "schedule:nightly", kind: .run),
            started("on-arrival", by: "trigger:new-page", kind: .run)
        ]
        let people = [started("mine", by: nil, kind: .run), started("theirs", by: "Ana on the studio Mac", kind: .run)]

        let kept = ActivityPaneFilter("started by: automatic").apply(automatic + people)

        #expect(kept.map(\.id) == automatic.map(\.id))
        let delete = ActivityPaneVerb.delete.split(kept)
        #expect(delete.targets.map(\.id) == automatic.map(\.id) && delete.skipped == 0, "⌘A then Delete takes what the filter leaves")
        #expect(ActivityPaneFilter("started by: schedule").apply(automatic + people).map(\.id) == ["nightly", "on-arrival"])
        #expect(ActivityPaneFilter("started by: Ana").apply(automatic + people).map(\.id) == ["theirs"])
    }

    /// `activity.pane.icons-say-source-and-kind` (#6441): "Kind" is a filter token, as "Started by" is.
    @Test("kind: keeps the rows of that kind, by the kind glyph's word or the engine's own kind")
    func kindToken() {
        func of(_ id: String, kind: String?) -> ActivityMonitorRow {
            var row = Fix.row(id, .done)
            row.engineKind = kind
            return row
        }
        let rows = [of("thumb", kind: "thumbnail"), of("read", kind: "read-a-page"), of("lines", kind: "find-lines"),
                    of("new", kind: "something-new"), of("none", kind: nil)]
        #expect(ActivityPaneFilter("kind: thumbnails").tokens == [.init(key: .kind, value: "thumbnails")])
        #expect(ActivityPaneFilter("kind: thumbnails").apply(rows).map(\.id) == ["thumb"])
        #expect(ActivityPaneFilter("kind: reading").apply(rows).map(\.id) == ["read"])
        #expect(ActivityPaneFilter("kind: find-lines").apply(rows).map(\.id) == ["lines"], "the engine's kind, for one with no word typed")
        #expect(ActivityPaneFilter("kind: something").apply(rows).map(\.id) == ["new"], "a kind with no glyph is found by its own name")
        #expect(ActivityPaneFilter("kind: thumbnails started by: you").apply(rows).map(\.id) == ["thumb"], "ANDed with the source")
    }

    @Test("date: today, a day and a range, in the person's own calendar")
    func dates() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Toronto")!
        let start = calendar.date(from: DateComponents(year: 2026, month: 11, day: 14, hour: 0, minute: 30))!
        #expect(ActivityPaneFilter.dateMatches("2026-11-14", start, now: start, calendar: calendar))
        #expect(ActivityPaneFilter.dateMatches("2026-11-13..2026-11-14", start, now: start, calendar: calendar))
        #expect(!ActivityPaneFilter.dateMatches("2026-11-13", start, now: start, calendar: calendar))
        #expect(ActivityPaneFilter.dateMatches("today", start, now: start, calendar: calendar))
    }

    @Test("the filter survives a relaunch through the pane's prefs")
    func persisted() {
        let data = ActivityPanePrefs.store(Data(), key: "pane") { $0.filter = "state: failed" }
        #expect(ActivityPanePrefs.load(data, key: "pane").filter == "state: failed")
    }

    /// `activity.pane.empty-says-one-line` (#6599).
    @Test("an empty pane says Nothing running in one line; a filter that hides every row says No activity matches")
    func emptyLine() {
        #expect(ActivityPane.emptyLine(rowsShown: 0, filterIsEmpty: true) == "Nothing running")
        #expect(ActivityPane.emptyLine(rowsShown: 0, filterIsEmpty: false) == "No activity matches")
        #expect(ActivityPane.emptyLine(rowsShown: 3, filterIsEmpty: true) == nil)
    }

    /// The launch alert's Choose… (#6584): the stopped rows, by job and project, are the rows selected.
    @Test("Choose…'s selections are the listed rows of those jobs in those projects, and no others")
    func revealAllPicksTheRows() {
        let project = UUID()
        var kept = ActivityPaneFixture.row("k", .paused)
        kept.libraryId = project
        var other = ActivityPaneFixture.row("o", .paused)
        other.libraryId = UUID()
        let ids = ActivityPane.rowIds(for: [ActivitySelection(jobId: "k", libraryId: project)], in: [kept, other])
        #expect(ids == ["k"])
    }
}
