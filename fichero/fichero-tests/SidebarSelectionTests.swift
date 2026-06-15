import Foundation
import Testing
@testable import Fichero

struct SidebarSelectionTests {
    @Test("#1165 sidebar tap fallback ignores already-selected rows")
    func tapFallbackIgnoresCurrentSelection() {
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:1") == nil)
    }

    @Test("#1165 sidebar tap fallback only requests missing selection")
    func tapFallbackRequestsDifferentSelection() {
        #expect(sidebarSelectionFallback(current: nil, tapped: "doc:1") == "doc:1")
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:2") == "doc:2")
    }

    @Test("#1736 Open in New Tab captures the originating window before opening")
    func openInNewTabCapturesHostWindowBeforeOpen() throws {
        let source = try appSource("Views/OpenAffordances.swift")
        let hostCapture = try #require(source.range(of: "let hostWindow = NSApp.keyWindow ?? NSApp.mainWindow"))
        // Prefix with indentation to skip the docstring comment at line 34 and match the code call.
        let openCall = try #require(source.range(of: "\n            openWindow(id: \"main\")"))

        #expect(hostCapture.lowerBound < openCall.lowerBound)
        #expect(source.contains("hostWindow.addTabbedWindow(newWindow, ordered: .above)"))
    }

    @Test("#1736 Open in New Window disables automatic tabbing")
    func openInNewWindowDisablesAutomaticTabbing() throws {
        let source = try appSource("Views/OpenAffordances.swift")

        #expect(source.contains("NSWindow.allowsAutomaticWindowTabbing = false"))
        #expect(source.contains("newWindow.tabbingMode = .disallowed"))
    }
}

private func appSource(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("fichero")
        .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
}
