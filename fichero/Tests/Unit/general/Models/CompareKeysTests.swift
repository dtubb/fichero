@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The compare view's keys, pager and spoken labels (`wide.compare.keyboard-and-voiceover`, `wide.compare.compact-layout`).
struct CompareKeysTests {
    private func made(_ platform: CompareViewModel.Platform = .mac) throws -> CompareViewModel {
        let json = """
        {"page_id":"p1","readers":[{"id":"a","label":"Reader a","kind":"candidate"},
         {"id":"b","label":"Reader b","kind":"candidate"}],
         "lines":[
          {"order":0,"differs":false,"picked_by_person":false,"segment_id":"s0",
           "readings":[{"reader_id":"a","text":"que","representation_id":"ra0"},
           {"reader_id":"b","text":"que","representation_id":"rb0"}],"words":[]},
          {"order":1,"differs":true,"picked_by_person":false,"segment_id":"s1",
           "readings":[{"reader_id":"a","text":"Yten","representation_id":"ra1"},
           {"reader_id":"b","text":"Item","representation_id":"rb1"}],"words":[]}]}
        """
        let answer = try JSONDecoder().decode(Components.Schemas.CompareReadersResponse.self, from: Data(json.utf8))
        return CompareViewModel(answer: answer, platform: platform)
    }

    @Test("the key map is one table")
    func table() {
        #expect(CompareViewModel.command(for: .leftArrow, option: false) == .previousCandidate)
        #expect(CompareViewModel.command(for: .rightArrow, option: false) == .nextCandidate)
        #expect(CompareViewModel.command(for: .upArrow, option: false) == .previousLine)
        #expect(CompareViewModel.command(for: .downArrow, option: false) == .nextLine)
        #expect(CompareViewModel.command(for: .downArrow, option: true) == .nextDifferingLine)
        #expect(CompareViewModel.command(for: .digit(2), option: false) == .showCandidate(2))
        #expect(CompareViewModel.command(for: .digit(7), option: false) == nil)
        #expect(CompareViewModel.command(for: .return, option: false) == .useThis)
        #expect(CompareViewModel.command(for: .escape, option: false) == .close)
    }

    @Test("down walks the lines; Option-down jumps to the next that differs")
    func lines() throws {
        var model = try made()
        #expect(model.apply(.nextLine) == .moved && model.focusedLine == 0)
        #expect(model.apply(.nextDifferingLine) == .moved && model.focusedLine == 1)
        #expect(model.apply(.nextDifferingLine) == .nothing)
        #expect(model.apply(.previousLine) == .moved && model.focusedLine == 0)
    }

    @Test("digits show one candidate or all; left and right move between candidates")
    func candidates() throws {
        var model = try made()
        _ = model.apply(.showCandidate(2))
        #expect(model.visibleReaders.map(\.id) == ["b"])
        _ = model.apply(.showCandidate(0))
        #expect(model.visibleReaders.count == 2)
        _ = model.apply(.nextCandidate)
        #expect(model.candidate == 0)
    }

    @Test("in Wipe the arrows move the handle, kept inside the picture")
    func wipeHandle() throws {
        var model = try made()
        model.mode = .wipe
        _ = model.apply(.nextCandidate)
        #expect(abs(model.handle - 0.55) < 0.0001)
    }

    @Test("Return uses the focused differing line's other reading; Escape closes")
    func useAndClose() throws {
        var model = try made()
        _ = model.apply(.nextDifferingLine)
        if case .useThis(_, let line) = model.apply(.useThis) { #expect(line == 1) } else { Issue.record("expected useThis") }
        #expect(model.apply(.close) == .close)
    }

    @Test("iPad and iPhone page the candidates with Overlay by default; the Mac shows all columns")
    func compact() throws {
        #expect(CompareViewModel.usesPager(.iPhone) && CompareViewModel.usesPager(.iPad) && !CompareViewModel.usesPager(.mac))
        let phone = try made(.iPhone)
        #expect(phone.mode == .overlay && phone.visibleReaders.count == 1 && phone.pagerDots == [true, false])
        #expect(try made(.mac).visibleReaders.count == 2)
    }

    @Test("columns, cells and rows are spoken as named things")
    func labels() throws {
        let model = try made()
        #expect(model.cellLabel(reader: model.readers[0], text: "Yten") == "Reader a: Yten")
        #expect(model.cellLabel(reader: model.readers[1], text: nil) == "Reader b: no reading")
        #expect(model.rowAnnouncement(model.rows[0]).hasSuffix("agree") && model.rowAnnouncement(model.rows[1]).hasSuffix("differ"))
    }
}
