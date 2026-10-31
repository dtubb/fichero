@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The chain strip's rows (`wide.chain.strip-on-the-page`, #5386): the engine's steps in its order, the reads-this mark where the
/// engine put it, a passed-over reason carried through, and no strip where nothing was written.
struct RenditionChainStripTests {
    private func chain(_ steps: String) throws -> Components.Schemas.ImageChain {
        let json = #"{"page_id":"p","read_from":"rendition","why":"w","steps":\#(steps),"passed_over":[],"axis":[]}"#
        return try JSONDecoder().decode(Components.Schemas.ImageChain.self, from: Data(json.utf8))
    }

    private let photo = #"{"kind":"photograph","role":"original","operation":"As it came in","figure":"the photograph","reads_this":false}"#
    private let straighten = #"{"kind":"rendition","rendition_id":"r1","role":"deskewed","operation":"Straighten","figure":"straightened 1.2°","reads_this":true}"#
    private let clarity = #"{"kind":"rendition","rendition_id":"r2","role":"prepared","operation":"Clarity","figure":"contrast raised","reads_this":false,"passed_over":"could not be read"}"#

    @Test("rows follow the engine's order and carry its words and marks")
    func rowsFollowTheEngine() throws {
        let rows = RenditionChainRow.rows(of: try chain("[\(photo),\(straighten),\(clarity)]"))
        #expect(rows.map(\.title) == ["As it came in", "Straighten", "Clarity"])
        #expect(rows.map(\.readsThis) == [false, true, false])
        #expect(rows[2].passedOver == "could not be read")
        #expect(rows[0].renditionId == nil)
    }

    @Test("a page with only its photograph shows no strip")
    func photographAlone() throws {
        #expect(!RenditionChainRow.isWorthShowing(RenditionChainRow.rows(of: try chain("[\(photo)]"))))
        #expect(RenditionChainRow.isWorthShowing(RenditionChainRow.rows(of: try chain("[\(photo),\(straighten)]"))))
    }
}
