@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.log.like-xcode` (#6588, decision 36): the Inspector's log is Xcode's: one line per row with its number, level
/// glyph, time and text; lines selected one or many (click, shift, command); Copy copies the selected lines (all when none);
/// find highlights each match and steps through them. A record: nothing edits it.
struct ActivityLogListTests {
    private func lines() throws -> [ActivityJobLogLine] {
        let json = """
        [{"timestamp": "2026-11-15T14:05:01+00:00", "level": "info", "message": "Reading page 1", "job_id": "j"},
         {"timestamp": "2026-11-15T14:05:03+00:00", "level": "warning", "message": "Page 2 is faint", "job_id": "j"},
         {"timestamp": "2026-11-15T14:05:04+00:00", "level": "error", "message": "Failed: page 3 unreadable", "job_id": "j"},
         {"timestamp": "2026-11-15T14:05:09+00:00", "level": "debug", "message": "page 3 retried", "job_id": "j"}]
        """
        let decoded = try JSONDecoder().decode([Components.Schemas.JobLogLine].self, from: Data(json.utf8))
        return decoded.enumerated().map { ActivityJobLogLine(index: $0.offset, $0.element) }
    }

    @Test("each level has its glyph: an error a red octagon, a warning a yellow triangle, info and debug quiet")
    func glyphs() {
        #expect(ActivityLogList.glyph("error").symbol == "xmark.octagon.fill")
        #expect(ActivityLogList.glyph("warning").symbol == "exclamationmark.triangle.fill")
        #expect(ActivityLogList.glyph("info").symbol == "info.circle")
        #expect(ActivityLogList.glyph("debug").symbol == "ladybug")
    }

    @Test("a click selects a line, shift extends from the last click, command adds or removes one")
    func selection() {
        var pick = ActivityLogList.Selection()
        pick.click(2, shift: false, command: false)
        #expect(pick.lines == [2])
        pick.click(0, shift: true, command: false)
        #expect(pick.lines == [0, 1, 2])
        pick.click(1, shift: false, command: true)
        #expect(pick.lines == [0, 2])
        pick.click(3, shift: false, command: false)
        #expect(pick.lines == [3])
    }

    @Test("Copy copies the selected lines in order, or the whole log when none is selected")
    func copy() throws {
        let log = try lines()
        #expect(ActivityLogList.copyText(log, selected: [2, 0]).components(separatedBy: "\n").count == 2)
        #expect(ActivityLogList.copyText(log, selected: [2, 0]).hasPrefix(log[0].plainText))
        #expect(ActivityLogList.copyText(log, selected: []).components(separatedBy: "\n").count == 4)
    }

    @Test("find matches whatever case, says which of how many, and steps round")
    func find() throws {
        let log = try lines()
        let found = ActivityLogList.matches(log, query: "PAGE 3")
        #expect(found == [2, 3])
        #expect(ActivityLogList.matchWords(current: 0, of: found.count) == "1 of 2")
        #expect(ActivityLogList.step(0, of: 2, forward: true) == 1 && ActivityLogList.step(1, of: 2, forward: true) == 0)
        #expect(ActivityLogList.step(0, of: 2, forward: false) == 1)
        #expect(ActivityLogList.matches(log, query: "  ").isEmpty)
        #expect(ActivityLogList.matchWords(current: 0, of: 0) == "No match")
    }

    @Test("a match is highlighted in the line's text, every time it occurs")
    func highlight() {
        let text = ActivityLogList.highlighted("page 3 then Page 3", query: "page 3")
        let marked = text.runs.filter { $0.backgroundColor != nil }.count
        #expect(marked == 2)
    }
}
