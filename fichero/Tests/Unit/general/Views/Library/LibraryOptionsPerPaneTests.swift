@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// #5280, `panes.options-per-pane`, ruled 2026-10-01: each pane remembers its own filter and
/// metadata settings. The Library's column visibility, sort by folder, dates lozenge and entity
/// kind filter were `@SceneStorage` (one value per WINDOW, so two Library panes in one window
/// overwrote each other) or `@AppStorage` (one value for the whole app); they are `@PaneStorage`
/// now. This drives the real property wrapper in hosted views, as two panes would: if it fell back
/// to one shared value, or did not read back what was saved, two panes would share it again.
@MainActor
final class LibraryOptionsPerPaneTests: XCTestCase {
    private let key = "test.libraryOptionsPerPane.\(UUID().uuidString)"

    override func tearDown() {
        EngineConfig.defaults.removeObject(forKey: key)
        EngineConfig.defaults.removeObject(forKey: key + ".byPane")
        super.tearDown()
    }

    /// What a probe saw when it appeared.
    private final class Seen { var value: String? }

    /// A pane's option: reads it when it appears, or writes `write`, as a menu would.
    private struct Probe: View {
        @PaneStorage var value: String
        let write: String?
        let seen: Seen

        init(key: String, write: String?, seen: Seen) {
            _value = PaneStorage(wrappedValue: "unset", key)
            self.write = write
            self.seen = seen
        }

        var body: some View {
            Color.clear.onAppear {
                if let write { value = write } else { seen.value = value }
            }
        }
    }

    /// Host a pane with this id until its probe has appeared; what it read, when it only reads.
    @discardableResult
    private func show(pane: UUID?, writing write: String? = nil) async throws -> String? {
        let seen = Seen()
        let window = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 200, height: 40),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let view = NSHostingView(rootView: Probe(key: key, write: write, seen: seen)
            .environment(\.paneLeafId, pane)
            // The test's own suite, never the app's domain (#4221): @AppStorage reads this.
            .defaultAppStorage(EngineConfig.defaults))
        window.contentView = view
        defer { window.contentView = nil }
        for _ in 0..<100 {
            view.layoutSubtreeIfNeeded()
            if write == nil, seen.value != nil { break }
            if write != nil, EngineConfig.defaults.string(forKey: key) == write { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        return seen.value
    }

    func testTwoPanesKeepTheirOwnValueAndBothSurviveARelaunch() async throws {
        let left = UUID(), right = UUID()
        try await show(pane: left, writing: "sorted by name")
        try await show(pane: right, writing: "sorted by date")
        // Fresh views over what was saved: a relaunch.
        let leftAgain = try await show(pane: left)
        let rightAgain = try await show(pane: right)
        XCTAssertEqual(leftAgain, "sorted by name", "the right pane's choice overwrote the left's")
        XCTAssertEqual(rightAgain, "sorted by date")
    }

    func testANewPaneStartsFromTheLastChoiceMadeAnywhere() async throws {
        try await show(pane: UUID(), writing: "dates hidden")
        let fresh = try await show(pane: UUID())
        XCTAssertEqual(fresh, "dates hidden")
    }
}
#endif
