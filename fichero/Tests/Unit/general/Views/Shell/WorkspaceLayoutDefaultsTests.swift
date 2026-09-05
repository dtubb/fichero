@testable import Fichero
import Foundation
import XCTest

/// "Make sure workspace is saved when we quit — panes reset each time."
/// (Daniel, 2026-09-04.)
///
/// The panes are `@SceneStorage`: per-window state SwiftUI persists through
/// macOS scene restoration, which a quit does not guarantee. The pane WIDTHS
/// beside them always survived because they are `@AppStorage` — plain
/// UserDefaults, not restoration-dependent. That asymmetry was the bug.
final class WorkspaceLayoutDefaultsTests: XCTestCase {

    /// An isolated store per test: these keys are real user preferences, and a
    /// test that wrote `UserDefaults.standard` would change the layout of the
    /// developer's own app.
    private var store: UserDefaults!
    private let suiteName = "WorkspaceLayoutDefaultsTests"

    override func setUp() {
        super.setUp()
        UserDefaults().removePersistentDomain(forName: suiteName)
        store = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        UserDefaults().removePersistentDomain(forName: suiteName)
        store = nil
        super.tearDown()
    }

    // MARK: - The round trip

    func testAHiddenPaneStaysHiddenAcrossARelaunch() {
        let left = PaneVisibility(grid: true, canvas: false, reading: true)
        WorkspaceLayoutDefaults.remember(left, chat: false, in: store)

        // A "relaunch" is exactly this: a fresh read of the store.
        XCTAssertEqual(WorkspaceLayoutDefaults.rememberedVisibility(in: store), left)
        XCTAssertFalse(WorkspaceLayoutDefaults.pane(.chat, default: true, in: store))
    }

    func testEveryPaneCombinationRoundTrips() {
        for grid in [true, false] {
            for canvas in [true, false] {
                for reading in [true, false] where grid || canvas || reading {
                    let layout = PaneVisibility(grid: grid, canvas: canvas, reading: reading)
                    WorkspaceLayoutDefaults.remember(layout, chat: grid, in: store)
                    XCTAssertEqual(
                        WorkspaceLayoutDefaults.rememberedVisibility(in: store), layout,
                        "\(layout) did not survive the round trip"
                    )
                }
            }
        }
    }

    func testTheLayoutModeRoundTrips() {
        WorkspaceLayoutDefaults.setLayoutModeRaw(LayoutMode.standard.rawValue, in: store)
        XCTAssertEqual(
            WorkspaceLayoutDefaults.layoutModeRaw(default: LayoutMode.widescreen.rawValue, in: store),
            LayoutMode.standard.rawValue
        )
    }

    // MARK: - Absent is not "off"

    /// The bug this guards is subtle and would ship looking deliberate:
    /// `UserDefaults.bool(forKey:)` answers `false` for a key never written,
    /// so a first-run window would open with every pane HIDDEN — which the
    /// #1696 invariant would then have to rescue.
    func testNoStoredPreferenceMeansTheDefault() {
        XCTAssertTrue(WorkspaceLayoutDefaults.pane(.grid, default: true, in: store))
        XCTAssertFalse(WorkspaceLayoutDefaults.pane(.grid, default: false, in: store))
        XCTAssertEqual(
            WorkspaceLayoutDefaults.rememberedVisibility(in: store),
            PaneVisibility(grid: true, canvas: true, reading: true),
            "A first run opens with the panes on, as it always did."
        )
    }

    func testTheStoredLayoutModeFallsBackWhenAbsent() {
        XCTAssertEqual(
            WorkspaceLayoutDefaults.layoutModeRaw(default: LayoutMode.widescreen.rawValue, in: store),
            LayoutMode.widescreen.rawValue
        )
    }

    // MARK: - Never a layout no window may open in

    /// A store written before #1696, or edited by hand, could name an
    /// all-hidden layout. Reading it back must not hand a window an empty
    /// content area — the invariant is enforced on the way OUT as well as in.
    func testAnAllHiddenStoredLayoutIsRefusedOnRead() {
        store.set(false, forKey: WorkspaceLayoutDefaults.Key.grid.rawValue)
        store.set(false, forKey: WorkspaceLayoutDefaults.Key.canvas.rawValue)
        store.set(false, forKey: WorkspaceLayoutDefaults.Key.reading.rawValue)

        let restored = WorkspaceLayoutDefaults.rememberedVisibility(in: store)
        XCTAssertTrue(
            restored.isAnyVisible,
            "No window may open with every content pane hidden (#1696)."
        )
    }

    /// What `setPaneVisible` stores has already passed the invariant, so the
    /// pair cannot record a layout it would refuse to apply.
    func testWhatTheMutationPathStoresIsAlwaysOpenable() {
        var visibility = PaneVisibility(grid: true, canvas: false, reading: false)
        // Hiding the last visible pane is refused by the invariant…
        visibility = visibility.settingVisible(.grid, false)
        WorkspaceLayoutDefaults.remember(visibility, chat: false, in: store)
        XCTAssertTrue(WorkspaceLayoutDefaults.rememberedVisibility(in: store).isAnyVisible)
    }

    // MARK: - What is deliberately NOT remembered

    /// The sidebar and inspector have a dozen PROGRAMMATIC writers — a
    /// claim-source reveal, an AppleScript `show panel`, a search summoning its
    /// chrome. Mirroring those would record a transient reveal as the user's
    /// chosen workspace, so they are out, and so is `sidebarMode` with its
    /// twenty writers.
    func testOnlyTheDeliberatelyChosenSurfacesAreRemembered() {
        XCTAssertEqual(
            Set(WorkspaceLayoutDefaults.Key.allCases.map(\.rawValue)),
            [
                "workspace.showDocumentGrid",
                "workspace.showDocumentCanvas",
                "workspace.showReadingPane",
                "workspace.showChatPane",
                "workspace.currentLayoutMode"
            ],
            """
            A key was added or removed. Anything remembered here must have ONE \
            deliberate mutation path — that is what separates a workspace the \
            user chose from a panel something revealed on their behalf.
            """
        )
    }

    /// The seam that made the bug invisible for so long: the panes are seeded
    /// from the store, and the ONE mutation path writes back to it.
    func testTheSeedAndTheWriteBackAreBothWired() throws {
        let contentView = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView.swift"),
            encoding: .utf8
        )
        let paneVisibility = try String(
            contentsOf: AppSource.root().appendingPathComponent("Views/Shell/PaneVisibility.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(contentView.contains("WorkspaceLayoutDefaults.showDocumentGrid"))
        XCTAssertTrue(contentView.contains("WorkspaceLayoutDefaults.showReadingPane"))
        XCTAssertTrue(
            paneVisibility.contains("WorkspaceLayoutDefaults.remember(next, chat: showChatPane)"),
            "Seeding without a write-back remembers the first-run layout forever."
        )
    }
}
