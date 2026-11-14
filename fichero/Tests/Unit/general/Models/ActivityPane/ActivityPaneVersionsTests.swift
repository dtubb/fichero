//
//  ActivityPaneVersionsTests.swift — `activity.pane.versions-are-siblings` (#6441): a step that ran more than once lists
//  its versions side by side in the Inspector, newest first, the newest done one counting.
//

@testable import Fichero
import Foundation
import Testing

struct ActivityPaneVersionsTests {
    @Test("Read run twice with two models: two versions naming each model, the second counts; Segment ran once: none")
    func readTwice() throws {
        let versions = ActivityPane.versions(of: ActivityPaneFixture.letters)
        let read = try #require(versions.first)
        #expect(versions.count == 1)
        #expect(read.step == "Read")
        #expect(read.versions.map(\.model) == ["Qwen 2 VL", "Kraken"])
        #expect(read.versions.map(\.counts) == [true, false])
    }

    @Test("the Inspector reads a selected run's versions from the run as listed, though its shown row holds files")
    func versionsOfTheShownRow() throws {
        let all = [ActivityPaneFixture.letters, ActivityPaneFixture.names]
        let shown = try #require(ActivityPane.outline(all).first { $0.id == "letters" })
        #expect(ActivityPane.versions(of: shown).isEmpty, "the outline's run row holds files, not steps")
        #expect(ActivityPane.versions(for: shown, in: all).map(\.step) == ["Read"])
        let file = try #require(shown.children?.first)
        #expect(ActivityPane.versions(for: file, in: all).map(\.step) == ["Read"], "a file row shows its run's versions")
    }

    @Test("retrying one failed page adds a version holding that one page")
    func onePageRetry() throws {
        let fixture = ActivityPaneFixture.self
        let run = fixture.row("run", .done, kind: .run, name: "Letters", children: [
            fixture.row("read1", .partial, kind: .step, name: "Read", model: "Kraken", done: 1, total: 2,
                        children: [fixture.page("a-p1", .done, doc: "p1"), fixture.page("a-p2", .failed, doc: "p2")]),
            fixture.row("read2", .done, kind: .step, name: "Read", model: "Kraken", done: 1, total: 1,
                        children: [fixture.page("b-p2", .done, doc: "p2")])
        ])
        let read = try #require(ActivityPane.versions(of: run).first)
        #expect(read.versions.map(\.id) == ["read2", "read1"], "newest first")
        #expect(read.versions.first?.total == 1, "the retry holds the one page")
    }
}
