@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `source.onboard.routes-for-the-volume` (#4951): Ready lists the routes side by side with each figure's basis in the engine's words;
/// a figure without a value says it is unknown and never a made-up one.
struct RouteWordsTests {
    private func route(_ json: String) throws -> RouteWords {
        RouteWords(try JSONDecoder().decode(Components.Schemas.Route.self, from: Data(json.utf8)))
    }

    @Test func aFigureNamesItsBasisAndAnUnknownOneSaysSo() throws {
        let words = try route("""
        {"id":"cloud","title":"Read it all with a cloud model","pages":1000,
         "cost_usd":{"value":12.4,"basis":"estimate","from":"price list x per-page tokens"},
         "time_seconds":{"basis":"unknown","from":"not measured yet"},
         "accuracy_cer":{"basis":"unknown","from":"run the bake-off"},"leaves_this_mac":true}
        """)
        #expect(words.cost == "Cost \((12.4).formatted(.currency(code: "USD"))) · estimate")
        #expect(words.time == "Time unknown")
        #expect(words.accuracy == "Error rate unknown")
        #expect(words.leavesThisMac)
    }

    @Test func aMeasuredTimeIsInUnitsAndNoFigureAtAllIsUnknown() throws {
        let words = try route("""
        {"id":"this-mac","title":"Read it all on this Mac","pages":1000,
         "time_seconds":{"value":9000,"basis":"measured","from":"median of this Mac's finished pages"},
         "accuracy_cer":{"value":0.041,"basis":"measured","from":"checked pages"},"leaves_this_mac":false}
        """)
        #expect(words.time.hasSuffix("· measured") && words.time.hasPrefix("Time "))
        #expect(words.cost == "Cost unknown", "no cost figure is unknown, not free")
        #expect(words.accuracy.hasSuffix("· measured"))
        #expect(!words.leavesThisMac)
    }
}
