import SwiftUI

/// The one style for every button and menu in a pane head or a bottom bar (`panes.chrome.bar-buttons-accessory-style`):
/// on macOS the accessory-bar style, a bezel on hover and a fill while pressed, as Xcode's filter bar and jump bar;
/// on iPad and iPhone the borderless look they have always had.
enum PaneBarStyle {
    enum Kind: Equatable {
        case accessoryBar, borderless
    }

    /// What this platform's bars wear.
    nonisolated static var kind: Kind {
        #if os(macOS)
        .accessoryBar
        #else
        .borderless
        #endif
    }

    /// Whether a bottom bar or the inspector strip is flat in the pane's material (`panes.chrome.bars-flush-on-mac`):
    /// on macOS, as Xcode's; iPad and iPhone keep the floating glass island.
    nonisolated static var barIsFlush: Bool {
        #if os(macOS)
        true
        #else
        false
        #endif
    }

    /// Whether a bar draws its one hairline, above a bottom bar and below a top strip (`panes.chrome.bar-hairline-rule`):
    /// always on macOS, where the bar is flush; the glass island on touch needs none.
    nonisolated static var barsDrawHairline: Bool { barIsFlush }
}

/// A bar's surface: on macOS the pane's own opaque background, flat and edge to edge, so rows scrolling beneath never
/// show through (owner 2026-11-13: "not translucent", like the sidebar's and Xcode's); the glass island elsewhere.
private struct PaneBarSurface: ViewModifier {
    let cornerRadius: CGFloat

    func body(content: Content) -> some View {
        #if os(macOS)
        content.background(.background)
        #elseif os(visionOS)
        content.background(.regularMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
        #else
        GlassEffectContainer {
            content.glassEffect(.regular, in: RoundedRectangle(cornerRadius: cornerRadius))
        }
        #endif
    }
}

extension View {
    /// A bottom bar's or strip's surface (`panes.chrome.bars-flush-on-mac`): flat on macOS, a glass island on touch.
    func paneBarSurface(cornerRadius: CGFloat = 8) -> some View {
        modifier(PaneBarSurface(cornerRadius: cornerRadius))
    }

    /// A pane-bar button: the accessory-bar style on macOS, borderless on touch.
    @ViewBuilder
    func paneBarButtonStyle() -> some View {
        #if os(macOS)
        buttonStyle(.accessoryBar)
        #else
        buttonStyle(.borderless)
        #endif
    }

    /// A pane-bar menu: a button menu in the accessory-bar style on macOS, the borderless button menu on touch.
    @ViewBuilder
    func paneBarMenuStyle() -> some View {
        #if os(macOS)
        menuStyle(.button).buttonStyle(.accessoryBar)
        #else
        menuStyle(.borderlessButton)
        #endif
    }
}
