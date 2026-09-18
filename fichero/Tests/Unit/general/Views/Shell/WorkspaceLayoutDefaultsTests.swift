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

    // MARK: - The last-applied PaneList (#4686)

    /// Encode/decode round trip through an isolated store — the same shape as every other
    /// remembered value here, just Data instead of a Bool.
    func testRememberedPaneListRoundTripsThroughUserDefaults() {
        let list = PaneList([.leaf(.library), .leaf(.preview), .leaf(.reading)])
        WorkspaceLayoutDefaults.rememberPaneList(list, in: store)
        let restored = WorkspaceLayoutDefaults.rememberedPaneList(in: store)
        XCTAssertEqual(restored, list)
        // Ids round-trip too — a restored workspace re-applies the SAME leaves, not fresh ones.
        XCTAssertEqual(restored?.nodes.map(\.id), list.nodes.map(\.id))
    }

    /// Nothing remembered yet (a fresh install, or a store predating #4686) answers nil — the
    /// caller's job to fall back to the Read default, the same "absent is not a value" contract
    /// `pane(_:default:)` already uses for the Bools.
    func testNoRememberedPaneListReturnsNilSoTheCallerCanFallBackToRead() {
        XCTAssertNil(WorkspaceLayoutDefaults.rememberedPaneList(in: store))
    }

    /// The mount-time seed is wired: `ContentView.activePaneList` seeds from
    /// `rememberedPaneList()`, falling back to the Read default (spec workspaces
    /// non-optionality untouched). The WRITE-BACK side is one funnel
    /// (`PaneVisibility.syncLegacyPaneVisibilityBools()`, #4686/#4687) — pinned separately below
    /// by `testEveryActivePaneListWriterCallsTheOneFunnel`, not here.
    func testThePaneListSeedIsWired() throws {
        let contentView = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(
            contentView.contains(
                "WorkspaceLayoutDefaults.rememberedPaneList() ?? BuiltInWorkspaceLayout.read.panes"),
            "activePaneList must mount from the remembered list, falling back to Read when absent."
        )
        let paneVisibility = try String(
            contentsOf: AppSource.root().appendingPathComponent("Views/Shell/PaneVisibility.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(
            paneVisibility.contains("WorkspaceLayoutDefaults.rememberPaneList(activePaneList)"),
            "The funnel is where the applied composition gets remembered for the next launch."
        )
    }

    /// Structural guardrail (#4686/#4687): every KNOWN `activePaneList` mutation site must be
    /// followed, within a few lines, by the ONE funnel (`syncLegacyPaneVisibilityBools()`) that
    /// syncs the legacy Bools AND remembers the composition for the next launch. A new writer
    /// that skips it silently reintroduces both the stale-checkmark bug and the
    /// forgets-on-relaunch bug at once.
    func testEveryActivePaneListWriterCallsTheOneFunnel() throws {
        let paneVisibility = try String(
            contentsOf: AppSource.root().appendingPathComponent("Views/Shell/PaneVisibility.swift"),
            encoding: .utf8
        )
        let layoutChooser = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+LayoutChooser.swift"),
            encoding: .utf8
        )
        let paneSpec = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/Layout/PaneSpec.swift"),
            encoding: .utf8
        )

        assertFunnelFollows(paneVisibility, after: "activePaneList = nextList")
        assertFunnelFollows(layoutChooser, after: "activePaneList = layout.panes")
        assertFunnelFollows(layoutChooser, after: "activePaneList = paneList")
        assertFunnelFollows(layoutChooser, after: "activePaneList = BuiltInWorkspaceLayout.read.panes")
        assertFunnelFollows(layoutChooser, after: "activePaneList = activePaneList.splittingLeaf(id, axis: axis)")
        assertFunnelFollows(paneSpec, after: "activePaneList = activePaneList.removingLeaf(id)")
        assertFunnelFollows(paneSpec, after: "activePaneList = activePaneList.changingLeafKind(id, to: kind)")
    }

    /// `source` must contain `marker`, and `"syncLegacyPaneVisibilityBools()"` must appear within
    /// `window` characters after it — a source-level "the funnel is right here, not forgotten a
    /// few refactors later" check.
    private func assertFunnelFollows(
        _ source: String, after marker: String, window: Int = 500,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        guard let range = source.range(of: marker) else {
            XCTFail("Mutation site moved or was renamed — marker not found: \(marker)", file: file, line: line)
            return
        }
        let snippet = String(source[range.upperBound...].prefix(window))
        XCTAssertTrue(
            snippet.contains("syncLegacyPaneVisibilityBools()"),
            "No funnel call within \(window) characters after: \(marker)",
            file: file, line: line
        )
    }
}
