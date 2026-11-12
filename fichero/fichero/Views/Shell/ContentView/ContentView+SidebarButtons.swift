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

    private static let buttonSize = CGSize(width: 28, height: 24)

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
    }

    private func button(
        symbol: String, title: String, help: String, isLit: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol)
                .labelStyle(.iconOnly)
                .font(.title3)
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
    @ToolbarContentBuilder
    var sidebarToolbarContent: some ToolbarContent {
        if sidebarPairHome == .sidebarColumn {
            ToolbarItem(placement: .automatic) {
                sidebarButtons
            }
        }
    }

    /// The pair as its own island in the window toolbar while the sidebar is hidden
    /// (`leadingToolbarContent`). The item turns the shared glass off and draws its own capsule,
    /// so it can never fuse with Back/Forward.
    var sidebarButtonsIsland: some View {
        sidebarButtons
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .glassEffect(.regular, in: Capsule())
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
