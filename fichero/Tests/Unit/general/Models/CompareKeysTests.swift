@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The compare view's keys, pager and spoken labels (`wide.compare.keyboard-and-voiceover`, `wide.compare.compact-layout`).
struct CompareKeysTests {
    private func model(_ platform: CompareViewModel.Platform = .mac) throws -> CompareViewModel {
        let json = """
        {"page_id":"p1","readers":[{"id":"a","label":"Reader a","kind":"candidate"},{"id":"b","label":"Reader b","kind":"candidate"}],
         "lines":[
          {"order":0,"differs":false,"picked_by_person":false,"segment_id":"s0","readings":[{"reader_id":"a","text":"que","representation_id":"ra0"},{"reader_id":"b","text":"que","representation_id":"rb0"}],"words":[]},
          {"order":1,"differs":true,"picked_by_person":false,"segment_id":"s1","readings":[{"reader_id":"a","text":"Yten","representation_id":"ra1"},{"reader_id":"b","text":"Item","representation_id":"rb1"}],"words":[]}]}
        """
        let answer = try JSONDecoder().decode(Components.Schemas.CompareReadersResponse.self, from: Data(json.utf8))
        return CompareViewModel(answer: answer, platform: platform)
    }

    @Test("the key map is one table")
    func table() {
        #expect(CompareViewModel.command(for: .left, option: false) == .previousCandidate)
        #expect(CompareViewModel.command(for: .right, option: false) == .nextCandidate)
        #expect(CompareViewModel.command(for: .up, option: false) == .previousLine)
        #expect(CompareViewModel.command(for: .down, option: false) == .nextLine)
        #expect(CompareViewModel.command(for: .down, option: true) == .nextDifferingLine)
        #expect(CompareViewModel.command(for: .digit(2), option: false) == .showCandidate(2))
        #expect(CompareViewModel.command(for: .digit(7), option: false) == nil)
        #expect(CompareViewModel.command(for: .return, option: false) == .useThis)
        #expect(CompareViewModel.command(for: .escape, option: false) == .close)
    }

    @Test("down walks the lines; Option-down jumps to the next that differs")
    func lines() throws {
        var m = try model()
        #expect(m.apply(.nextLine) == .moved && m.focusedLine == 0)
        #expect(m.apply(.nextDifferingLine) == .moved && m.focusedLine == 1)
        #expect(m.apply(.nextDifferingLine) == .nothing)
        #expect(m.apply(.previousLine) == .moved && m.focusedLine == 0)
    }

    @Test("digits show one candidate or all; left and right move between candidates")
    func candidates() throws {
        var m = try model()
        _ = m.apply(.showCandidate(2))
        #expect(m.visibleReaders.map(\.id) == ["b"])
        _ = m.apply(.showCandidate(0))
        #expect(m.visibleReaders.count == 2)
        _ = m.apply(.nextCandidate)
        #expect(m.candidate == 0)
    }

    @Test("in Wipe the arrows move the handle, kept inside the picture")
    func wipeHandle() throws {
        var m = try model()
        m.mode = .wipe
        _ = m.apply(.nextCandidate)
        #expect(abs(m.handle - 0.55) < 0.0001)
    }

    @Test("Return uses the focused differing line's other reading; Escape closes")
    func useAndClose() throws {
        var m = try model()
        _ = m.apply(.nextDifferingLine)
        if case .useThis(_, let line) = m.apply(.useThis) { #expect(line == 1) } else { Issue.record("expected useThis") }
        #expect(m.apply(.close) == .close)
    }

    @Test("iPad and iPhone page the candidates with Overlay by default; the Mac shows all columns")
    func compact() throws {
        #expect(CompareViewModel.usesPager(.iPhone) && CompareViewModel.usesPager(.iPad) && !CompareViewModel.usesPager(.mac))
        let phone = try model(.iPhone)
        #expect(phone.mode == .overlay && phone.visibleReaders.count == 1 && phone.pagerDots == [true, false])
        #expect(try model(.mac).visibleReaders.count == 2)
    }

    @Test("columns, cells and rows are spoken as named things")
    func labels() throws {
        let m = try model()
        #expect(m.cellLabel(reader: m.readers[0], text: "Yten") == "Reader a: Yten")
        #expect(m.cellLabel(reader: m.readers[1], text: nil) == "Reader b: no reading")
        #expect(m.rowAnnouncement(m.rows[0]).hasSuffix("agree") && m.rowAnnouncement(m.rows[1]).hasSuffix("differ"))
    }
}
