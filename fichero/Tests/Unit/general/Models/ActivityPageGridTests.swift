//
//  ActivityPageGridTests.swift
//  FicheroTests
//
//  activity.window.page-grid (#5960): one dot per page for a stage, in the engine's order, with the page and its reason on hover.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct ActivityPageGridTests {
    private func grid(total: Int = 4) throws -> ActivityPageGrid {
        let json = """
        {"job_id": "run", "stage": "read", "total": \(total), "offset": 0, "items": [
          {"document_id": "p3", "name": "p3.jpg", "state": "done", "stages": {"read": "done"}},
          {"document_id": "p1", "name": "p1.jpg", "state": "failed", "reason": "The model returned nothing", "stages": {"read": "failed"}},
          {"document_id": "p2", "name": "p2.jpg", "state": "running", "stages": {"read": "running"}},
          {"document_id": "p4", "name": "p4.jpg", "state": "waiting", "reason": "Waiting: the model lane", "stages": {}}]}
        """
        return ActivityPageGrid(try JSONDecoder().decode(Components.Schemas.RunPageStates.self, from: Data(json.utf8)))
    }

    @Test("the dots keep the engine's order, not Finder order, and each has its state")
    func order() throws {
        let grid = try grid()
        #expect(grid.pages.map(\.id) == ["p3", "p1", "p2", "p4"])
        #expect(grid.pages.map(\.dot) == [.done, .failed, .running, .waiting])
    }

    @Test("hovering a failed or waiting dot says the page and its reason; a done one just the page")
    func help() throws {
        let pages = try grid().pages
        #expect(pages[0].help == "p3.jpg")
        #expect(pages[1].help == "p1.jpg: The model returned nothing")
        #expect(pages[3].help == "p4.jpg: Waiting: the model lane")
    }

    @Test("pages the read did not carry are counted, not drawn")
    func notShown() throws {
        #expect(try grid(total: 4).notShown == 0)
        #expect(try grid(total: 270).notShown == 266)
        #expect(try grid().count(.failed) == 1)
    }

    @Test("an unknown state is grey and not known, never done; one summary label stands for the grid")
    func unknownAndSummary() throws {
        let json = """
        {"job_id": "run", "total": 5, "items": [
          {"document_id": "a", "name": "a", "state": "done"}, {"document_id": "b", "name": "b", "state": "done"},
          {"document_id": "c", "name": "c", "state": "failed"}, {"document_id": "d", "name": "d", "state": "waiting"}]}
        """
        let grid = ActivityPageGrid(try JSONDecoder().decode(Components.Schemas.RunPageStates.self, from: Data(json.utf8)))
        #expect(grid.summary == "5 pages: 2 read, 1 failed, 1 waiting (4 shown)")
        let odd = ActivityPageGrid(pages: [.init(id: "x", name: "x", dot: .unknown, help: "x")], total: 1)
        #expect(odd.count(.done) == 0)
        #expect(odd.summary == "1 page: 1 not known")
    }

    @Test("the stage chooser offers only stages that ran, and sits outside the grid so All stages is always one pick away")
    func stagesThatRan() throws {
        func card(_ id: String, _ state: ActivityStageCardState) -> ActivityDetails.StageCard {
            .init(id: id, title: id, state: state, done: 0, total: 0, made: [], why: nil, offersSetUp: false, failed: nil, pagesFailed: 0)
        }
        let cards = [card("find", .done), card("read", .running), card("names", .waiting), card("dates", .notRun),
                     card("describe", .skipped), card("x", .failed), card("y", .partial)]
        #expect(ActivityPageGrid.stagesThatRan(cards).map(\.id) == ["find", "read", "x", "y"])
        let view = try String(contentsOf: try AppSource.root().appendingPathComponent("Views/Activity/Detail/ActivityDetailsView.swift"),
                              encoding: .utf8)
        let picker = try #require(view.range(of: #"Picker("Stage""#))
        let grid = try #require(view.range(of: "if let grid = store.pageGrids"))
        #expect(picker.lowerBound < grid.lowerBound, "the chooser is before the grid's if-let, not inside it")
    }

    @Test("VoiceOver can open the pages that need a look: failed first, then running, then waiting, labelled with their state")
    func accessibleOpen() throws {
        let grid = try grid()
        #expect(grid.pages.map(\.accessibilityLabel) == ["p3.jpg, read", "p1.jpg, failed", "p2.jpg, reading", "p4.jpg, waiting"])
        #expect(grid.actionPages.map(\.id) == ["p1", "p2", "p4"], "no action for a done page: its dot is clicked")
        let many = ActivityPageGrid(pages: (0..<80).map { .init(id: "f\($0)", name: "f\($0)", dot: .failed, help: "") }, total: 80)
        #expect(many.actionPages.count == ActivityPageGrid.actionLimit)
        #expect(ActivityPageGrid.showAllTitle == "Show the run's pages…", "one action reaches the done pages too")
        let view = try String(contentsOf: try AppSource.root().appendingPathComponent("Views/Activity/Detail/ActivityPageGridView.swift"),
                              encoding: .utf8)
        #expect(view.contains("Button(ActivityPageGrid.showAllTitle)"))
    }
}
