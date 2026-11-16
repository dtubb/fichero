@testable import Fichero
import Foundation
import Testing

/// The Inspector's segment pane in groups (`source.editor.inspector-segment-pane-is-laid-out-in-groups`, #6413): the order
/// of the groups, empty sections hidden behind one Add menu, and Details on one line.
struct InspectorSegmentLayoutTests {
    private func row(_ key: String, _ value: String, _ origin: String = "set by a person, for the project") -> InspectorLanguage.Row {
        .init(key: key, title: key.capitalized, value: value, origin: origin, basis: "")
    }

    @Test("the groups come in order: Readings, Details, History, Links and Rights")
    func groupOrder() {
        #expect(InspectorSegmentLayout.Group.allCases.map(\.title) == ["Readings", "Details", "History", "Links and Rights"])
    }

    @Test("an empty section hides and is offered in Add; one asked for, or one holding something, shows")
    func emptySectionsHideBehindAdd() {
        let empty: Set<InspectorSegmentLayout.Addition> = [.hand, .certaintyMark]
        #expect(InspectorSegmentLayout.hides(.hand, empty: empty, revealed: []))
        #expect(InspectorSegmentLayout.addMenu(empty: empty, revealed: []).map(\.title) == ["Hand", "Certainty Mark"])
        #expect(!InspectorSegmentLayout.hides(.hand, empty: empty, revealed: [.hand]))
        #expect(InspectorSegmentLayout.addMenu(empty: empty, revealed: [.hand]) == [.certaintyMark])
        #expect(!InspectorSegmentLayout.hides(.certaintyMark, empty: [.hand], revealed: []))
        #expect(InspectorSegmentLayout.addMenu(empty: [], revealed: []).isEmpty)
    }

    @Test("Details says language, script and direction in words on one line; unknown ones are left out")
    func detailsLine() {
        let english = Locale(identifier: "en")
        let rows = [row("language", "es"), row("script", "Latn"), row("direction", "Left to Right", "from the script"),
                    row("encoding", "UTF-8")]
        #expect(InspectorSegmentLayout.detailsLine(rows, locale: english) == "Spanish · Latin · Left to Right")
        #expect(InspectorSegmentLayout.detailsLine([row("language", "la"), row("script", "Not determined")], locale: english)
                == "Latin")
        #expect(InspectorSegmentLayout.detailsLine([row("language", "Unknown")], locale: english) == nil)
    }

    @Test("Details' tooltip says where each value came from")
    func detailsHelp() {
        let help = InspectorSegmentLayout.detailsHelp([row("language", "es"), row("script", "Not determined")])
        #expect(help == "Language: set by a person, for the project\nScript: Not determined")
    }
}
