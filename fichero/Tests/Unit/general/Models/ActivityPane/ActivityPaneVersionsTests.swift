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
}
