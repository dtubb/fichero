//
//  ActivityPaneFiltersTests.swift — `activity.pane.history-kept-and-filterable` (#6441): `key: value` tokens ANDed over
//  both groupings, remembered per pane; history stays in the same table.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneFiltersTests {
    typealias F = ActivityPaneFixture

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
        let rows = ActivityPane.byFile([F.letters])
        let kept = ActivityPaneFilter("model: Kraken state: failed").apply(rows)
        #expect(kept.map(\.documentId) == ["p2"])
        #expect(kept.first?.children?.map(\.name) == ["Letters › Read"])
        #expect(ActivityPaneFilter("").apply(rows) == rows)
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
}
