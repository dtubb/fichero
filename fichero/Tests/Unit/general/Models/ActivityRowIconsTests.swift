//
//  ActivityRowIconsTests.swift
//  FicheroTests
//
//  #6441 `activity.pane.icons-say-source-and-kind`: the source and the kind of a row map to one symbol each, in one place.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityRowIconsTests {
    @Test("started_by maps to the four sources; a name is a person")
    func sources() {
        typealias Row = ActivityMonitorRow
        #expect(Row.source(startedBy: "automatic") == .automatic)
        #expect(Row.source(startedBy: "import") == .automatic)
        #expect(Row.source(startedBy: "schedule:nightly") == .schedule)
        #expect(Row.source(startedBy: "workflow") == .recipe)
        #expect(Row.source(startedBy: "read-again:thread-1") == .recipe)
        #expect(Row.source(startedBy: "owner") == .person)
        #expect(Row.source(startedBy: nil) == .person)
        #expect(Row.Source.automatic.symbol == "gearshape.arrow.triangle.2.circlepath")
        #expect(Row.Source.person.word == "Started by you")
    }

    @Test("task_type maps to a kind glyph with its word; an unknown kind has none")
    func kinds() {
        typealias Row = ActivityMonitorRow
        #expect(Row.kindSymbol(engineKind: "read-a-page")?.symbol == "text.viewfinder")
        #expect(Row.kindSymbol(engineKind: "find-lines")?.symbol == "rectangle.split.3x1")
        #expect(Row.kindSymbol(engineKind: "find-names-tag-words")?.word == "Names and statements")
        #expect(Row.kindSymbol(engineKind: "kraken-page")?.symbol == "scribble")
        #expect(Row.kindSymbol(engineKind: "thumbnail")?.symbol == "photo")
        #expect(Row.kindSymbol(engineKind: "embedding")?.symbol == "magnifyingglass")
        #expect(Row.kindSymbol(engineKind: "run-a-recipe")?.symbol == "list.bullet.rectangle")
        #expect(Row.kindSymbol(engineKind: "something-new") == nil)
        #expect(Row.kindSymbol(engineKind: nil) == nil)
    }
}
