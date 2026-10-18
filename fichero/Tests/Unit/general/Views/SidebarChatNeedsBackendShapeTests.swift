@testable import Fichero
import XCTest

/// #5396 item 5: the sidebar chat pane is not mounted while the backend is
/// unreachable (an offline phone showed a useless composer). Source-shape guard.
@MainActor
final class SidebarChatNeedsBackendShapeTests: XCTestCase {
    func testSidebarChatIsGatedOnBackendRunning() throws {
        let source = try AppSource.code("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift")
        let gate = try XCTUnwrap(source.range(of: "if showChatPane,"))
        let head = String(source[gate.lowerBound...].prefix(120))
        XCTAssertTrue(head.contains("appState.isBackendRunning"), "the chat pane no longer waits for the backend")
    }
}
