@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.window.now-upnext-done-today` (#5960): a three-stage run is one row in NOW with three segments; a waiting run is in UP NEXT;
/// a finished run is in DONE TODAY; the row has exactly one button whose label follows the run's state.
struct ActivityOneBarTests {
    private func block(state: String) throws -> Components.Schemas.LiveBlock {
        let stages = #"[{"stage":"prepare-images","title":"Prepare Images","state":"done","done":20,"failed":0,"total":20},"#
            + #"{"stage":"read","title":"Read","state":"running","done":7,"failed":1,"total":20},"#
            + #"{"stage":"names","title":"Names","state":"waiting","done":0,"failed":0,"total":0}]"#
        let json = #"{"id":"r1","recipe":"Mosquera","state":"\#(state)","done":7,"failed":1,"left":12,"total":20,"stages":\#(stages)}"#
        return try JSONDecoder().decode(Components.Schemas.LiveBlock.self, from: Data(json.utf8))
    }

    @Test("a three-stage run is one row in NOW with three segments filled as pages finish")
    func segments() throws {
        let bar = ActivityOneBar(block: try block(state: "running"))
        #expect(bar.section == .now && bar.segments.count == 3)
        #expect(bar.segments.map(\.fill) == [1, 0.35, 0])
        #expect(bar.segments[1].failed == 1 && bar.segments.map(\.title) == ["Prepare Images", "Read", "Names"])
    }

    @Test("a waiting run is UP NEXT, a finished one DONE TODAY, a paused one still NOW")
    func sections() throws {
        #expect(ActivityOneBar(block: try block(state: "waiting")).section == .upNext)
        #expect(ActivityOneBar(block: try block(state: "done")).section == .doneToday)
        #expect(ActivityOneBar(block: try block(state: "paused")).section == .now)
    }

    @Test("one button whose label follows the state: Pause, Resume, Retry, none once done")
    func button() throws {
        #expect(ActivityOneBar(block: try block(state: "running")).buttonTitle == "Pause")
        #expect(ActivityOneBar(block: try block(state: "paused")).buttonTitle == "Resume")
        #expect(ActivityOneBar(block: try block(state: "failed")).buttonTitle == "Retry")
        #expect(ActivityOneBar(block: try block(state: "done")).buttonTitle == nil)
    }
}
