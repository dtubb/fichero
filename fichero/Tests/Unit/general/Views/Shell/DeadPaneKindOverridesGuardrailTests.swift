@testable import Fichero
import XCTest

/// A forbidden-pattern absence guardrail, split out of `WindowWorkspaceTests` (#5052) so that
/// file's 23 behaviour tests are not exempt from the capability-scrape ratchet with it.
@MainActor
final class DeadPaneKindOverridesGuardrailTests: XCTestCase {
    /// `paneKindOverrides` lost its last READER when #4685 deleted `focusedSplitStorageKey`'s
    /// `SplitCommandRouting.storageKey(overrides:)` call — the live `ContentView.paneKindOverrides`
    /// dict it populated is never subscripted anywhere in the app any more. The `WindowLayoutSnapshot`
    /// field stays (decode-only, for an old snapshot that has it), but neither `captureLayoutSnapshot`
    /// nor `applyLayoutSnapshot` should populate it — a source guardrail, since neither method is
    /// unit-runnable without a live `ContentView`.
    func testCaptureAndApplyNoLongerPopulateTheDeadPaneKindOverrides() throws {
        let layoutChooser = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+LayoutChooser.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(
            layoutChooser.contains("paneKindOverrides: paneKindOverrides"),
            "captureLayoutSnapshot must not populate the dead paneKindOverrides field")
        XCTAssertFalse(
            layoutChooser.contains("paneKindOverrides = snapshot.paneKindOverrides"),
            "applyLayoutSnapshot must not restore into the dead live paneKindOverrides dict")
    }
}
