import XCTest

@testable import Fichero

/// Unit tests for the pure inline/overflow split behind the sidebar mode strip's
/// narrow-width fallback (#3059, parent #2670): `.library` and the selected mode
/// are always kept inline; the rest fill inline in order up to the limit and the
/// remainder overflows.
final class SidebarModeBarPartitionTests: XCTestCase {

    func testAllInlineWhenAtOrUnderLimit() {
        let modes: [SidebarMode] = [.library, .search, .chat]
        let result = SidebarModeBar.partition(modes: modes, selected: .library, limit: 4)
        XCTAssertEqual(result.inline, modes)
        XCTAssertTrue(result.overflow.isEmpty)
    }

    func testOverflowsBeyondLimitInOrder() {
        let modes: [SidebarMode] = [.library, .search, .chat, .workflows, .research, .automation]
        let result = SidebarModeBar.partition(modes: modes, selected: .library, limit: 3)
        XCTAssertEqual(result.inline, [.library, .search, .chat])
        XCTAssertEqual(result.overflow, [.workflows, .research, .automation])
    }

    func testSelectedModeIsAlwaysInlineEvenWhenLate() {
        let modes: [SidebarMode] = [.library, .search, .chat, .workflows, .research, .automation]
        // .automation is last and past the limit, but selected → must stay inline.
        let result = SidebarModeBar.partition(modes: modes, selected: .automation, limit: 3)
        XCTAssertEqual(result.inline, [.library, .search, .chat, .automation])
        XCTAssertEqual(result.overflow, [.workflows, .research])
        XCTAssertFalse(result.overflow.contains(.automation))
    }

    func testLibraryIsAlwaysInlineEvenIfSelectionIsElsewhere() {
        let modes: [SidebarMode] = [.library, .search, .chat, .workflows]
        let result = SidebarModeBar.partition(modes: modes, selected: .workflows, limit: 2)
        XCTAssertTrue(result.inline.contains(.library))
        XCTAssertTrue(result.inline.contains(.workflows))
    }

    func testInlineOrderIsPreserved() {
        let modes: [SidebarMode] = [.library, .search, .chat, .workflows, .research]
        let result = SidebarModeBar.partition(modes: modes, selected: .research, limit: 2)
        let inlineIndices = result.inline.map { modes.firstIndex(of: $0)! }
        XCTAssertEqual(inlineIndices, inlineIndices.sorted())
    }

    func testNonPositiveLimitReturnsAllInline() {
        let modes: [SidebarMode] = [.library, .search]
        let result = SidebarModeBar.partition(modes: modes, selected: .library, limit: 0)
        XCTAssertEqual(result.inline, modes)
        XCTAssertTrue(result.overflow.isEmpty)
    }
}
