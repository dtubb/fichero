@testable import Fichero
import XCTest

/// The stall profile's dominant class (stalls.log 2026-08-24: ~340s/day of
/// main-thread time inside value-witness copies of SidebarView /
/// ReaderToolbar / DocumentTabView / Document) is a function of these types'
/// VALUE SIZE — every graph update copies them through gesture and
/// conditional wrappers. This test is the measurement the slimming program
/// works from, and a ratchet: a type that grows past its recorded ceiling
/// fails here BEFORE it grows the stall log.
///
/// Ceilings = measured 2026-08-25 values + headroom (Document 400,
/// SidebarView 1088, ReaderToolbar 592, DocumentTabView 713, LibraryView
/// 3672, ContentView 4832): room for a field or two, a hard stop for
/// another embedded array. NOTE the declared structs are the multiplier,
/// not the whole cost — the copies the stall log sampled are of the
/// COMPOSED body values (nested _ConditionalContent/gesture generics),
/// which the #4331 AnyView caps bound at case boundaries.
final class ViewValueSizeTests: XCTestCase {
    private func assertSize<T>(_ type: T.Type, atMost ceiling: Int) {
        let size = MemoryLayout<T>.size
        print("view-value-size: \(String(describing: type)) = \(size) bytes")
        XCTAssertLessThanOrEqual(
            size, ceiling,
            "\(type) grew past \(ceiling) bytes — every main-thread graph "
            + "update copies this value; shrink or box before shipping "
            + "(see stalls.log 2026-08-24 analysis)"
        )
    }

    func testStallImplicatedValueSizes() {
        assertSize(Document.self, atMost: 512)
        assertSize(SidebarView.self, atMost: 1536)
        assertSize(ReaderToolbar.self, atMost: 1024)
        assertSize(DocumentTabView.self, atMost: 1024)
        assertSize(LibraryView.self, atMost: 4096)
        // 5632 → 5760 (workspaces state) → 5824 (2026-08-30 evening: the
        // run-context SceneStorage string). Next growth should box the
        // workspace + bar state into one reference instead of raising this.
        assertSize(ContentView.self, atMost: 5824)
    }
}
