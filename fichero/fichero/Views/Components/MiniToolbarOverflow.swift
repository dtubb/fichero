import SwiftUI

/// The tiers a mini-toolbar row can render inline (#3056, parent #2670).
/// `essential` verbs are always inline; `secondary` verbs are inline only when
/// there is room (regular/macOS) and otherwise collapse into the overflow menu.
enum MiniToolbarTier: String, CaseIterable, Equatable {
    case essential
    case secondary
}

/// Pure, testable platform-tiering policy for `AdaptiveMiniToolbarRow`. It owns
/// only the *per-platform button budget* — which tiers are eligible to render
/// inline for a width class — NOT pixel fitting, which `ViewThatFits` owns.
/// Kept separate from the view so the budget logic is unit-testable (#3056).
enum MiniToolbarTierPolicy {
    /// On compact width (iPhone) only the `essential` tier is inline; secondary
    /// items live in the trailing overflow `Menu` — the essentials-only idiom
    /// (#2670). On regular width / macOS both tiers are eligible inline, and
    /// `ViewThatFits` then decides whether they actually fit.
    static func inlineTiers(isCompact: Bool) -> [MiniToolbarTier] {
        isCompact ? [.essential] : [.essential, .secondary]
    }
}

/// A reusable adaptive mini-toolbar row that gives every bar the same
/// per-platform button budget + graceful overflow, instead of each bar
/// hand-rolling `ViewThatFits` (as `ReaderToolbar` / `WorkflowToolbar` do today).
/// Slice 1 of the mini-toolbar unification (#3056, parent #2670).
///
/// - **compact width (iPhone):** `essential` inline + a trailing `ellipsis.circle`
///   `Menu` holding the secondary items.
/// - **regular / macOS:** `ViewThatFits(in: .horizontal)` — first candidate is
///   `essential` + `secondary` inline; the fallback is `essential` inline + the
///   overflow `Menu`. The bar never extends past its pane.
///
/// The caller supplies `overflowMenu` — a `Label`-based mirror of the secondary
/// buttons — the same pattern as `ReaderToolbar.overflowMenu`.
struct AdaptiveMiniToolbarRow<Essential: View, Secondary: View, OverflowMenu: View>: View {
    private let essential: Essential
    private let secondary: Secondary
    private let overflow: OverflowMenu

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    init(
        @ViewBuilder essential: () -> Essential,
        @ViewBuilder secondary: () -> Secondary,
        @ViewBuilder overflowMenu: () -> OverflowMenu
    ) {
        self.essential = essential()
        self.secondary = secondary()
        self.overflow = overflowMenu()
    }

    private var isCompact: Bool { horizontalSizeClass == .compact }

    var body: some View {
        // Derive layout from the pure policy so the budget logic isn't buried in
        // the view. On macOS `horizontalSizeClass` is nil (not `.compact`), so
        // the Mac correctly takes the regular `ViewThatFits` path.
        if MiniToolbarTierPolicy.inlineTiers(isCompact: isCompact).contains(.secondary) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    essential
                    secondary
                }
                HStack(spacing: 12) {
                    essential
                    overflowMenuButton
                }
            }
        } else {
            HStack(spacing: 12) {
                essential
                overflowMenuButton
            }
        }
    }

    /// Trailing `ellipsis.circle` menu holding the secondary items when they
    /// don't render inline. Sized to the shared touch target so the hit area is
    /// comfortable on iOS (mirrors the MiniToolbar metric policy).
    private var overflowMenuButton: some View {
        Menu {
            overflow
        } label: {
            Image(systemName: ToolbarSymbols.overflowMenu)
                .frame(
                    minWidth: MiniToolbar<EmptyView, EmptyView>.touchTargetSide,
                    minHeight: MiniToolbar<EmptyView, EmptyView>.touchTargetSide
                )
        }
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More actions")
        .accessibilityLabel("More toolbar actions")
    }
}
