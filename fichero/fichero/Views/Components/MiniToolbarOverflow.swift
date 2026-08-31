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
/// - **regular / macOS:** `ViewThatFits(in: .horizontal)` walks a LADDER of
///   candidates — roomy inline, tight inline, tight inline over the caller's
///   `condensed` coat of the same controls — and only then falls back to
///   `essential` inline + the overflow `Menu`. The bar never extends past its
///   pane, and it never collapses while the controls would still have fit.
///
/// The ladder is the fix for the greedy `…` (Daniel, 2026-08-31: "the ellipsis
/// is too greedy"). Two candidates meant ONE control too wide sent the whole
/// secondary tier into a menu — a bar with 40pt to spare rendered as `…`
/// because the roomy spacing, not the buttons, was what did not fit. Each rung
/// gives up the cheapest thing first: inter-item air, then labels (via
/// `condensed`), and only last the controls themselves.
///
/// The caller supplies `overflowMenu` — a `Label`-based mirror of the secondary
/// buttons — the same pattern as `ReaderToolbar.overflowMenu`. `condensed` is
/// optional: bars that have no tighter coat to offer get the 3-closure init and
/// the ladder simply reuses `secondary` for that rung.
struct AdaptiveMiniToolbarRow<Essential: View, Secondary: View, Condensed: View, OverflowMenu: View>: View {
    private let essential: Essential
    private let secondary: Secondary
    private let condensed: Condensed
    private let overflow: OverflowMenu

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    /// Roomy → tight inter-item spacing. Air is the first thing the ladder
    /// spends, because a user cannot tell 12pt from 6pt but can very much tell
    /// a visible button from a hidden one.
    private static var roomySpacing: CGFloat { 12 }
    private static var tightSpacing: CGFloat { 6 }

    init(
        @ViewBuilder essential: () -> Essential,
        @ViewBuilder secondary: () -> Secondary,
        @ViewBuilder condensed: () -> Condensed,
        @ViewBuilder overflowMenu: () -> OverflowMenu
    ) {
        self.essential = essential()
        self.secondary = secondary()
        self.condensed = condensed()
        self.overflow = overflowMenu()
    }

    private var isCompact: Bool { horizontalSizeClass == .compact }

    var body: some View {
        // Derive layout from the pure policy so the budget logic isn't buried in
        // the view. On macOS `horizontalSizeClass` is nil (not `.compact`), so
        // the Mac correctly takes the regular `ViewThatFits` path.
        if MiniToolbarTierPolicy.inlineTiers(isCompact: isCompact).contains(.secondary) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Self.roomySpacing) {
                    essential
                    secondary
                }
                HStack(spacing: Self.tightSpacing) {
                    essential
                    secondary
                }
                HStack(spacing: Self.tightSpacing) {
                    essential
                    condensed
                }
                HStack(spacing: Self.roomySpacing) {
                    essential
                    overflowMenuButton
                }
            }
        } else {
            HStack(spacing: Self.roomySpacing) {
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

extension AdaptiveMiniToolbarRow where Condensed == Secondary {
    /// The 3-closure form every existing bar uses (reader, sidebar, workflow):
    /// no separate condensed coat, so the ladder's condensed rung renders the
    /// same secondary content at the tighter spacing. Iterating rather than
    /// replacing — those call sites are untouched by the greedy-`…` fix.
    init(
        @ViewBuilder essential: () -> Essential,
        @ViewBuilder secondary: () -> Secondary,
        @ViewBuilder overflowMenu: () -> OverflowMenu
    ) {
        let tier = secondary()
        self.init(essential: essential, secondary: { tier }, condensed: { tier }, overflowMenu: overflowMenu)
    }
}
