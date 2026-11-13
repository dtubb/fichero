import SwiftUI

// MARK: - Sidebar buttons
//
// Split out of ContentView+Toolbar.swift, which is already over the file_length limit.

/// The two far-left buttons, as in Xcode (Daniel, 2026-11-11): the folder tree and the chat
/// conversations. Each lights while its part is up; the rules live in `SidebarColumnState`.
///
/// A view of its own, taking the state and one closure, so a preview can show every lit
/// combination without a window. ONE size wherever it sits: the default bordered style outside a
/// toolbar drew wide grey tiles with small glyphs, nothing like Xcode's compact icons.
struct SidebarPairButtons: View {
    let state: SidebarColumnState
    let apply: (SidebarColumnState) -> Void

    /// The pill behind each glyph, and the glyph's size inside it. iOS's `.title3` is 20 points against the Mac's 15, so on
    /// the iPad the glyph spilled past its 28 × 24 pill (owner, 2026-11-13): there it is `.body` in a 32 × 28 pill.
    #if os(iOS)
    private static let buttonSize = CGSize(width: 32, height: 28)
    private static let glyphFont = Font.body
    #else
    private static let buttonSize = CGSize(width: 28, height: 24)
    private static let glyphFont = Font.title3
    #endif

    var body: some View {
        HStack(spacing: 2) {
            button(
                symbol: "list.bullet",
                title: state.treeLit ? "Hide Sidebar" : "Show Sidebar",
                help: state.treeLit ? "Hide the sidebar" : "Show the sidebar",
                isLit: state.treeLit
            ) { apply(state.togglingTree()) }
            button(
                symbol: ToolbarSymbols.chatPane,
                title: state.chatLit ? "Hide Chat" : "Show Chat",
                help: state.chatLit ? "Hide the Chat" : "Show the Chat",
                isLit: state.chatLit
            ) { apply(state.togglingChat()) }
        }
        // Room inside the toolbar's glass capsule on both sides (owner, 2026-11-13: the list button sat tight against
        // the capsule's leading edge, on the Mac and the iPad).
        .padding(.horizontal, 6)
    }

    private func button(
        symbol: String, title: String, help: String, isLit: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol)
                .labelStyle(.iconOnly)
                .font(Self.glyphFont)
                .toolbarSurfaceLit(isLit)
        }
        .buttonStyle(SidebarPairButtonStyle(isLit: isLit, size: Self.buttonSize))
        .accessibilityLabel(title)
        .help(help)
    }
}

/// Xcode's navigator buttons: a soft grey pill (a capsule, not a rounded square) behind the one that is on, a lighter one
/// under the pointer, a darker one while pressed. The default borderless style has no hover at all.
private struct SidebarPairButtonStyle: ButtonStyle {
    let isLit: Bool
    let size: CGSize

    func makeBody(configuration: Configuration) -> some View {
        Tile(isLit: isLit, isPressed: configuration.isPressed, size: size) { configuration.label }
    }

    private struct Tile<Content: View>: View {
        let isLit: Bool
        let isPressed: Bool
        let size: CGSize
        @ViewBuilder let content: Content
        @State private var isHovering = false

        private var fillOpacity: Double {
            if isPressed { return 0.18 }
            if isLit { return 0.12 }
            return isHovering ? 0.07 : 0
        }

        var body: some View {
            content
                .frame(width: size.width, height: size.height)
                .background(Color.primary.opacity(fillOpacity), in: Capsule())
                .contentShape(Rectangle())
                .onHover { isHovering = $0 }
        }
    }
}

extension ContentView {
    var sidebarButtons: some View {
        SidebarPairButtons(state: sidebarColumnState, apply: applySidebarColumnState)
    }

    /// Where this window draws the pair (#6563, `SidebarPairHome`).
    var sidebarPairHome: SidebarPairHome? {
        SidebarPairHome.home(columnShown: showSidebar, isCompact: horizontalSizeClass == .compact)
    }

    /// The pair as a real toolbar item of the SIDEBAR column, placed `.automatic`: Apple's docs place those "in the
    /// current toolbar section in order of leading to trailing", so it starts beside the window controls. The earlier
    /// attempts failed: `.navigation` is hoisted into the detail toolbar beside Back/Forward, and drawing the pair
    /// over the title bar left part of it inside the strip macOS keeps for dragging the window, so clicks missed.
    /// On the iPad it is the top of the sidebar, where the system toggle was (#6563).
    /// The pair's place in the sidebar column's bar: `.automatic` on the Mac, which starts it beside the window controls;
    /// on the iPad `.automatic` put it at the column's trailing edge, so it is pinned leading, as on the Mac (#6563).
    static var sidebarPairPlacement: ToolbarItemPlacement {
        #if os(iOS)
        .topBarLeading
        #else
        .automatic
        #endif
    }

    /// Declared whenever the window has a pair at all, not only while the column is up: on the iPad a column whose bar
    /// had no items while hidden came back with no bar, so the pair was gone from the sidebar's top (#6563). The Mac
    /// removes the hidden column from the window, so this never draws a second pair there.
    /// The Mac draws the pair in the column only while the column is its home (#6558); the iPad declares it whenever
    /// the window has a pair, so a hidden-then-shown column keeps it (#6563).
    var showsSidebarPairInColumn: Bool {
        #if os(iOS)
        sidebarPairHome != nil
        #else
        sidebarPairHome == .sidebarColumn
        #endif
    }

    @ToolbarContentBuilder
    var sidebarToolbarContent: some ToolbarContent {
        if showsSidebarPairInColumn {
            ToolbarItem(placement: Self.sidebarPairPlacement) {
                // The island's breathing room here too: the column's glass pill hugged the pair, the sparkle on its edge.
                sidebarButtons.padding(.horizontal, 6)
            }
        }
    }

    /// The pair as its own island in the window toolbar while the sidebar is hidden
    /// (`leadingToolbarContent`). The item turns the shared glass off and draws its own capsule,
    /// so it can never fuse with Back/Forward.
    /// On iOS the bar's own capsule holds it, as every other item's does: a second, hand-drawn capsule made it taller
    /// than its neighbours (owner, 2026-11-13).
    @ViewBuilder
    var sidebarButtonsIsland: some View {
        #if os(iOS)
        sidebarButtons
        #else
        sidebarButtons
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .glassEffect(.regular, in: Capsule())
        #endif
    }
}

#if DEBUG
#Preview("Sidebar buttons: every state") {
    VStack(alignment: .leading, spacing: 14) {
        ForEach(
            [
                ("both", SidebarColumnState(columnShown: true, treeHidden: false, chatOn: true)),
                ("files only", SidebarColumnState(columnShown: true, treeHidden: false, chatOn: false)),
                ("chat only", SidebarColumnState(columnShown: true, treeHidden: true, chatOn: true)),
                ("closed", SidebarColumnState(columnShown: false, treeHidden: false, chatOn: false))
            ],
            id: \.0
        ) { label, state in
            HStack(spacing: 16) {
                Text(label).font(.caption).frame(width: 70, alignment: .leading)
                SidebarPairButtons(state: state, apply: { _ in })
                SidebarPairButtons(state: state, apply: { _ in })
                    .padding(.horizontal, 6)
                    .padding(.vertical, 4)
                    .glassEffect(.regular, in: Capsule())
            }
        }
    }
    .padding(20)
}
#endif
