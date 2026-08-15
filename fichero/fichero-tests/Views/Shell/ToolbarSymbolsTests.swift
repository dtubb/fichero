@testable import Fichero
import Foundation
import Testing

/// The chrome symbol audit (#4360) and its structural guardrails (#4361/#4362).
///
/// One glyph per meaning across the window toolbar, the status island, and the
/// shared mini-toolbar set: the defect class is two meanings sharing a symbol
/// (filter's three-lines-in-a-circle vs the old activity `list.bullet.circle`;
/// the library and preview pane toggles both decaying to a bare `rectangle`
/// when hidden), which teaches the user the symbol means nothing.
///
/// The material rules are source-anchored the same way the island's #3163
/// structure tests are: native Liquid Glass comes from the toolbar itself, so
/// any painted fill in this chrome IS the bug being guarded against.
struct ToolbarSymbolsTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Symbol uniqueness

    @Test("no two chrome meanings share a glyph")
    func noTwoMeaningsShareAGlyph() {
        var seen: [String: String] = [:]
        for entry in ToolbarSymbols.allByMeaning {
            if let holder = seen[entry.symbol] {
                Issue.record(
                    "\"\(entry.symbol)\" is used for both \"\(holder)\" and \"\(entry.meaning)\""
                )
            }
            seen[entry.symbol] = entry.meaning
        }
        #expect(seen.count == ToolbarSymbols.allByMeaning.count)
    }

    /// The reported #4360 duplicate, pinned forever: activity must never wear
    /// the filter's glyph (or its old circled-list near-twin).
    @Test("activity and filter are visually distinct")
    func activityAndFilterAreDistinct() {
        #expect(ToolbarSymbols.activityIdle != ToolbarSymbols.filter)
        #expect(ToolbarSymbols.activityIdle != "list.bullet.circle")
        #expect(!ToolbarSymbols.allByMeaning.contains { $0.symbol == "list.bullet.circle" })
    }

    /// One meaning, one glyph app-wide: the island's activity button opens the
    /// same Activity surface the sidebar lists, so it wears the sidebar's glyph.
    @Test("the activity glyph matches the sidebar's Activity category")
    func activityGlyphMatchesSidebar() {
        #expect(ToolbarSymbols.activityIdle == ItemCategory.activity.icon)
    }

    /// Closing a pane and clearing a text field are different meanings; the
    /// circled fill belongs to the platform's clear-field affordance.
    @Test("close pane does not wear the clear-field glyph")
    func closePaneIsNotClearField() {
        #expect(ToolbarSymbols.closePane != ToolbarSymbols.clearField)
    }

    // MARK: - Native material (no painted plates)

    /// #4360: the island sits in the toolbar's own Liquid Glass. The old
    /// `.quaternary.opacity(0.5)` fill rendered as an opaque plate (white-ish
    /// in dark appearance). No painted background may return.
    @Test("the status island paints no background of its own")
    func islandPaintsNoBackground() throws {
        let source = try Self.appSource("Views/Shell/Toolbar/StatusIslandToolbarItem.swift")
        #expect(!source.contains(".background("))
    }

    /// The breadcrumb lozenge fill and the hand-rolled `toolbarToggleIcon`
    /// highlight were custom approximations of the system's toolbar treatment.
    @Test("the window toolbar has no hand-rolled fills or highlights")
    func toolbarHasNoHandRolledFills() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!source.contains("toolbarToggleIcon"))
        #expect(!source.contains("Color.primary.opacity"))
        #expect(!source.contains(".background("))
    }

    /// Pane/filter/inspector state is the native `Toggle` on-state, not a
    /// glyph swap — so no toolbar control may fall back to a bare `rectangle`.
    @Test("toolbar toggles are native and keep constant glyphs")
    func toolbarTogglesAreNative() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!source.contains("\"rectangle\""))
        #expect(source.contains("Toggle(isOn:"))
    }

    /// The shared lozenge is the platform's `.accessoryBar` control, not a
    /// painted rounded rect with an accent fill and a hairline stroke.
    @Test("LozengeButton is the native accessory-bar control")
    func lozengeButtonIsNative() throws {
        let source = try Self.appSource("Views/Components/MiniToolbar.swift")
        #expect(source.contains(".accessoryBar"))
        // Assert on CODE, not prose: the doc comment above LozengeButton names
        // the strokeBorder it replaced, so a bare word match trips on itself.
        #expect(!source.contains(".strokeBorder("))
    }

    // MARK: - #4391 ready reads as ready, and names its transport

    /// The reported defect, both halves: (1) an outline glyph with no colour
    /// read as "disconnected" — and the first fix's filled HORIZONTAL bolt
    /// still decayed to a tilde-in-a-ring at 13 pt; (2) a local UDS engine and
    /// an engine on another machine shared one symbol. Ready is now two
    /// filled, legible glyphs chosen by ownership.
    @Test("engine ready is split by transport, both filled and legible")
    func engineReadyIsSplitByTransport() {
        #expect(ToolbarSymbols.engineReadyLocal == "bolt.circle.fill")
        #expect(ToolbarSymbols.engineReadyRemote == "antenna.radiowaves.left.and.right.circle.fill")
        // The tilde-reading horizontal bolt must not come back in any fill.
        #expect(!ToolbarSymbols.allByMeaning.contains { $0.symbol.hasPrefix("bolt.horizontal") })
    }

    @Test("the ready state paints its own colour and picks the glyph by ownership")
    func engineReadyHasItsOwnColor() throws {
        let source = try Self.appSource("Views/Shell/Toolbar/EngineStatusToolbarItem.swift")
        let readySection = source
            .components(separatedBy: "case .setupNeeded, .ready:")[1]
            .components(separatedBy: "\n        }")[0]
        #expect(readySection.contains(".foregroundStyle(.green)"))
        #expect(!readySection.contains(".foregroundStyle(.secondary)"))
        #expect(readySection.contains("ToolbarSymbols.engineReadyRemote"))
        #expect(readySection.contains("ToolbarSymbols.engineReadyLocal"))
    }

    /// A symbol can only hint; the popover NAMES the transport in text, from
    /// the same ownership input every surface receives (#4380/#4400).
    @Test("the ready popover text names local vs remote")
    func readyPopoverNamesTheTransport() {
        let local = ConnectionPresentation.status(
            phase: .ready, ownership: .appManaged, accessError: nil, authBroken: false
        )
        let remote = ConnectionPresentation.status(
            phase: .ready, ownership: .remote, accessError: nil, authBroken: false
        )
        #expect(local.detail.contains("this Mac"))
        #expect(remote.detail.contains("another machine"))
        #expect(local.symbol == ToolbarSymbols.engineReadyLocal)
        #expect(remote.symbol == ToolbarSymbols.engineReadyRemote)
        // externalLocal is still LOCAL — the split is transport, not ownership.
        let external = ConnectionPresentation.status(
            phase: .ready, ownership: .externalLocal, accessError: nil, authBroken: false
        )
        #expect(external.symbol == ToolbarSymbols.engineReadyLocal)
    }

    // MARK: - #4361 search placeholder

    /// The placeholder names the control, not a capability: it must read
    /// "Search", never a description of the Ask feature.
    ///
    /// #4407/#4521 moved the field itself: the window-level `.searchable`
    /// (whose `prompt:` this used to pin) is gone from the root layout, and
    /// the engine-search field now lives in the library's mini toolbar,
    /// summoned by the toolbar toggle. The placeholder rule rides along.
    @Test("the search field placeholder reads Search")
    func searchPlaceholderReadsSearch() throws {
        let layout = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(
            !layout.contains(".searchable("),
            "window-level search came back — it belongs to the library mini toolbar (#4407)"
        )
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("TextField(\"Search\", text:"))
        #expect(!mini.contains("Ask your library"))
    }

    // MARK: - #4362 mini-toolbar placement

    @Test("reader bars sit at the bottom on every platform")
    func readerPlacementIsOneDecision() {
        // Daniel 2026-08-11 (supersedes the Mac-top choice): "bottom of
        // library and reader is where we can filter, and where we can show
        // which metadata or columns to show" — the Xcode console model.
        // Touch already wanted bottom for reachability; the fork is gone.
        #expect(MiniToolbarPlacement.preferredForReader == .bottom)
    }

    /// The reader hosts the find bar through the shared component's placement
    /// decision — not a second hand-rolled bar on either edge.
    @Test("the reader find bar rides the shared placement policy")
    func readerFindBarUsesSharedPlacement() throws {
        let source = try Self.appSource("Views/Reader/Page/ReadingPaneView.swift")
        #expect(source.contains("MiniToolbarPlacement.preferredForReader == .top"))
        #expect(source.contains("PaneFilterBar(placement: .top) { readerFindBar }"))
        #expect(source.contains("PaneFilterBar(placement: .bottom) { readerFindBar }"))
    }
}
