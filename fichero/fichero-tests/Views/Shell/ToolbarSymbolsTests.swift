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

    // MARK: - #4391 ready reads as ready

    /// The reported defect: an outline glyph with no colour reads as
    /// "disconnected", not "ready". Filled shape + a colour of its own fixes
    /// the half of #4391 this fix scopes to (transport distinction is a
    /// separate, undone half — see the issue).
    @Test("engine ready is a filled glyph, not the bare outline")
    func engineReadyIsFilled() {
        #expect(ToolbarSymbols.engineReady == "bolt.horizontal.circle.fill")
        #expect(ToolbarSymbols.engineReady != "bolt.horizontal.circle")
    }

    @Test("the ready state paints its own colour, not .secondary")
    func engineReadyHasItsOwnColor() throws {
        let source = try Self.appSource("Views/Shell/Toolbar/EngineStatusToolbarItem.swift")
        let readySection = source
            .components(separatedBy: "case .setupNeeded, .ready:")[1]
            .components(separatedBy: "\n        }")[0]
        #expect(readySection.contains(".foregroundStyle(.green)"))
        #expect(!readySection.contains(".foregroundStyle(.secondary)"))
    }

    // MARK: - #4361 search placeholder

    /// The placeholder names the control, not a capability: it must read
    /// "Search", never a description of the Ask feature.
    @Test("the search field placeholder reads Search")
    func searchPlaceholderReadsSearch() throws {
        let source = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(source.contains("prompt: \"Search\""))
        #expect(!source.contains("Ask your library"))
    }

    // MARK: - #4362 mini-toolbar placement

    @Test("reader bars sit at the top on the Mac, bottom on touch")
    func readerPlacementIsOnePlatformDecision() {
        #if os(macOS)
        #expect(MiniToolbarPlacement.preferredForReader == .top)
        #else
        #expect(MiniToolbarPlacement.preferredForReader == .bottom)
        #endif
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
