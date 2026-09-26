@testable import Fichero
import Foundation
import XCTest

/// `ContentView.activePaneList`'s `@State` initial-value expression reads the remembered pane
/// list, and an initial-value expression runs on EVERY `ContentView.init`. That was a JSON
/// decode on the main thread per init (slowdown review, 2026-09-20). The read is memoised on the
/// stored bytes: these count real decoder runs through `paneListDecodeCount`.
///
/// The counter is process-wide and read-only from here; each test reads it before and after its
/// own synchronous calls, in an isolated store no other test writes.
final class RememberedPaneListMemoTests: XCTestCase {
    /// An isolated, empty store per test — never `.standard`, which is the app's own.
    private func freshStore(_ name: String) throws -> UserDefaults {
        let suite = "RememberedPaneListMemoTests.\(name)"
        UserDefaults().removePersistentDomain(forName: suite)
        return try XCTUnwrap(UserDefaults(suiteName: suite))
    }

    /// Two reads of unchanged defaults decode once.
    func testRepeatReadDoesNotDecode() throws {
        let store = try freshStore("repeat")
        let list = PaneList([.leaf(.library), .leaf(.preview)])
        WorkspaceLayoutDefaults.rememberPaneList(list, in: store)

        let before = WorkspaceLayoutDefaults.paneListDecodeCount
        let first = WorkspaceLayoutDefaults.rememberedPaneList(in: store)
        let second = WorkspaceLayoutDefaults.rememberedPaneList(in: store)
        let third = WorkspaceLayoutDefaults.rememberedPaneList(in: store)

        XCTAssertEqual(first, list)
        XCTAssertEqual(second, list)
        XCTAssertEqual(third, list)
        let decodes = WorkspaceLayoutDefaults.paneListDecodeCount - before
        XCTAssertEqual(decodes, 1, "a repeat read of the same bytes must not run the decoder")
    }

    /// A write invalidates: the next read decodes the new list.
    func testWriteInvalidates() throws {
        let store = try freshStore("write")
        let first = PaneList([.leaf(.library), .leaf(.preview)])
        let second = PaneList([.leaf(.library), .leaf(.reading), .leaf(.inspector)])

        WorkspaceLayoutDefaults.rememberPaneList(first, in: store)
        XCTAssertEqual(WorkspaceLayoutDefaults.rememberedPaneList(in: store), first)

        let before = WorkspaceLayoutDefaults.paneListDecodeCount
        WorkspaceLayoutDefaults.rememberPaneList(second, in: store)
        XCTAssertEqual(WorkspaceLayoutDefaults.rememberedPaneList(in: store), second, "a stale memo must never outlive a write")
        XCTAssertEqual(WorkspaceLayoutDefaults.paneListDecodeCount - before, 1)
    }

    /// Nothing remembered is nil, and is not memoised as a value.
    func testAbsentIsNil() throws {
        let store = try freshStore("absent")
        XCTAssertNil(WorkspaceLayoutDefaults.rememberedPaneList(in: store))

        let list = PaneList([.leaf(.library)])
        WorkspaceLayoutDefaults.rememberPaneList(list, in: store)
        XCTAssertEqual(WorkspaceLayoutDefaults.rememberedPaneList(in: store), list)
    }
}
