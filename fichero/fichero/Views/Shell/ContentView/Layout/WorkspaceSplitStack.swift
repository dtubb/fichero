import SwiftUI

/// A RESIZABLE stack for an applied workspace's splits. Lays 1–N child panes out along `axis`.
///
/// Each child is FLEX (fills the remainder), a HARD PIN (`Sizing.fixed`, absolute points — the film
/// strip, which should never grow with the display), or PROPORTIONAL (`Sizing.fraction`, a share of
/// the stack's own extent, resizable via a `ResizableDivider` once dragged) (#4688, CD 2026-09-17:
/// "think through % ... for the various default workspaces").
///
/// EVERYTHING is wrapped in a `GeometryReader` and every extent is CLAMPED to the available space —
/// the pattern `SplittablePane` uses. The previous version stacked TWO frames on each fixed child
/// (`.frame(width: fixed).frame(maxHeight: .infinity)`); when a stack was NESTED inside another, that
/// fed an unbounded size proposal into the AppKit-backed panes and AppKit's `_layoutSubtreeWithOldSize:`
/// never converged → the infinite-layout-recursion crash the CD hit (2026-09-16). One frame per child,
/// clamped, no `fixed → .infinity` pair.
struct WorkspaceSplitStack: View {
    /// One child of the stack's SIZING preference along the axis.
    enum Sizing: Equatable {
        /// Fills whatever the sized/pinned siblings leave over.
        case flex
        /// A HARD pin, absolute points — never resizable, never reads or writes the per-position
        /// stored drag state (#4688). The film strip: "a strip of page icons should not grow with
        /// the display" (CD 2026-09-16).
        case fixed(Double)
        /// A proportional seed — a share (0–1) of the stack's own extent — for a RESIZABLE column:
        /// seeded from this fraction the first time it's laid out, then a drag persists over it via
        /// `@SceneStorage`, same as an absolute default used to.
        case fraction(Double)

        /// A leaf's sizing preference from its `PaneConfig`: an absolute `paneExtent` always wins
        /// over a `paneFraction` on the same leaf. `nil` = no preference — the caller's flex/fallback
        /// rule decides. Pure: this is the "extent wins" contract WorkspaceSplitStackTests assert
        /// directly, without a ContentView or a PaneNode tree.
        static func preferred(extent: Double?, fraction: Double?) -> Sizing? {
            if let extent { return .fixed(extent) }
            if let fraction { return .fraction(fraction) }
            return nil
        }
    }

    /// One child of the stack.
    struct Child {
        let view: AnyView
        let sizing: Sizing

        init(_ view: AnyView, sizing: Sizing = .flex) {
            self.view = view
            self.sizing = sizing
        }
    }

    let axis: SplitAxis
    let children: [Child]

    // Up to two SIZED (proportional/resizable) child slots persist their extent per split position.
    // Every built-in split has at most two resizable children (a HARD-pinned film strip never uses
    // a slot, and the third pane, if any, flexes), so two slots suffice.
    // ponytail: two @SceneStorage slots, not an array — @SceneStorage needs fixed properties; a
    // 3rd resizable child would fall back to resolving fresh from its fraction every render (never
    // happens in the five built-ins).
    @SceneStorage private var extent0: Double
    @SceneStorage private var extent1: Double

    /// Sentinel meaning "never dragged" — @SceneStorage needs a concrete `Double` at init, before
    /// the `GeometryReader` below knows the stack's actual `total`. NOTHING ever seeds this to a
    /// resolved points value (SF3 review finding, fixed): converting a fraction to absolute
    /// points on first appear meant a 0.4-fraction column, seeded once at a 1000pt window, stayed
    /// pinned to 400pt forever — even after moving to a 2000pt display. `resolvedExtents` treats
    /// `unset` as "use the fraction of `total`", recomputed fresh every render, so the display
    /// value always tracks the CURRENT window size until an actual drag writes a real value here
    /// (the `.fraction` case's `Binding` setter in `arranged`, below — never its getter).
    private static let unset: Double = -1

    init(axis: SplitAxis, storageKey: String, children: [Child]) {
        self.axis = axis
        self.children = children
        self._extent0 = SceneStorage(wrappedValue: Self.unset, "wsplit.\(storageKey).0")
        self._extent1 = SceneStorage(wrappedValue: Self.unset, "wsplit.\(storageKey).1")
    }

    /// A workspace-unique storage-key component (#4688): `keyPath` alone is a tree POSITION
    /// ("0", "0.1", …), identical across every workspace, so Read's inner split and Transcribe's
    /// film strip — both at position "0" — shared one @SceneStorage slot ("drag Read's divider
    /// once, switch to Transcribe → the strip is the dragged height, not 72"). `leadingChildID` is a
    /// `PaneNode`'s own id, freshly generated per applied `PaneList`, so two different workspaces'
    /// splits at the same tree position never collide. `keyPath` stays in the key too, purely for
    /// human-readable debugging (e.g. in a `defaults read`).
    static func storageKey(keyPath: String, leadingChildID: UUID?) -> String {
        "\(keyPath)-\(leadingChildID?.uuidString ?? keyPath)"
    }

    var body: some View {
        GeometryReader { proxy in
            let total = axis == .horizontal ? proxy.size.width : proxy.size.height
            Group {
                if axis == .horizontal {
                    HStack(spacing: 0) { arranged(total: total) }
                } else {
                    VStack(spacing: 0) { arranged(total: total) }
                }
            }
            .frame(width: proxy.size.width, height: proxy.size.height)
        }
    }

    /// The stored slot value for each `.fraction` child, in child order — `nil` for a slot never
    /// seeded/dragged yet (so `resolvedExtents` falls back to its fraction of `total`), and `nil`
    /// for every non-`.fraction` child (fixed/flex have no stored slot).
    private func storedOverrides() -> [Double?] {
        var slot = 0
        return children.map { child in
            guard case .fraction = child.sizing else { return nil }
            defer { slot += 1 }
            let raw = slot == 0 ? extent0 : (slot == 1 ? extent1 : Self.unset)
            return raw == Self.unset ? nil : raw
        }
    }

    /// The children interleaved with dividers. A divider sits between a resizable child and the
    /// flexing content, on the side facing the flex, so dragging it resizes the resizable pane.
    /// Resizable children BEFORE the flex get the divider after them (drag toward trailing to
    /// grow); one AFTER the flex (a trailing strip) gets the divider before it (drag toward
    /// leading to grow). A HARD-pinned child (the film strip) never gets a divider — it's fixed,
    /// full stop (#4688).
    @ViewBuilder private func arranged(total: CGFloat) -> some View {
        let resolved = Self.resolvedExtents(children.map(\.sizing), storedOverrides: storedOverrides(), total: Double(total))
        let flexIndex = children.firstIndex { child in
            if case .flex = child.sizing { return true }
            return false
        } ?? max(0, children.count - 1)

        var slot = 0
        let plans: [ChildPlan] = children.enumerated().map { index, child in
            switch child.sizing {
            case .flex:
                return ChildPlan(view: child.view, layout: .flex)
            case .fixed:
                return ChildPlan(view: child.view, layout: .fixed(resolved[index] ?? 0))
            case .fraction:
                // SF3 review finding: this used to be `$extent0`/`$extent1` directly — a plain
                // pass-through to the raw @SceneStorage slot, which is WHY something had to seed
                // that slot with an absolute-points value before the divider had anything sane to
                // show or drag from. A COMPUTED binding instead: its getter is the already-resolved
                // display value (the fraction of `total` until a real drag has written a stored
                // override, per `resolvedExtents`/`storedOverrides` above), so nothing is ever
                // seeded — the fraction re-resolves fresh against whatever `total` is THIS render.
                // The setter is the only path that ever writes `extent0`/`extent1`, and it only
                // fires from `ResizableDivider`'s own drag handler — never from a mere appearance.
                let displayValue = resolved[index] ?? 0
                let isFirstFractionSlot = slot == 0
                let binding = Binding<Double>(
                    get: { displayValue },
                    set: { newValue in
                        if isFirstFractionSlot { extent0 = newValue } else { extent1 = newValue }
                    }
                )
                slot += 1
                return ChildPlan(
                    view: child.view,
                    layout: .resizable(binding, display: displayValue, dividerBefore: index > flexIndex)
                )
            }
        }
        ForEach(Array(plans.enumerated()), id: \.offset) { _, plan in
            switch plan.layout {
            case .flex:
                plan.view.frame(maxWidth: .infinity, maxHeight: .infinity)
            case let .fixed(value):
                sized(plan.view, value: value)
            case let .resizable(binding, display, dividerBefore):
                if dividerBefore { divider(binding, edge: .trailing, total: total) }
                sized(plan.view, value: display)
                if !dividerBefore { divider(binding, edge: .leading, total: total) }
            }
        }
    }

    /// How one child is laid out this render: filling the remainder, pinned to a fixed points
    /// value, or resizable — bound to a stored slot, displayed at its resolved (clamped) extent,
    /// with a divider on the side facing the flex.
    /// Sibling of `ChildPlan`, not nested inside it — three levels of nesting
    /// (stack > plan > layout) buys nothing and trips `nesting`.
    private enum ChildLayout {
        case flex
        case fixed(Double)
        case resizable(Binding<Double>, display: Double, dividerBefore: Bool)
    }

    private struct ChildPlan {
        let view: AnyView
        let layout: ChildLayout
    }

    /// A sized child at its resolved extent — already clamped, so this is a single, unconditional
    /// frame. ONE frame node: pin the axis via min == max, flex the cross axis. (`.frame(width:
    /// maxHeight:)` mixes two frame overloads and won't compile; the stacked
    /// `.frame(width:).frame(maxHeight:)` pair is the one that fed the unbounded proposal into
    /// AppKit and crashed. This is neither.)
    @ViewBuilder private func sized(_ view: AnyView, value: Double) -> some View {
        if axis == .horizontal {
            view.frame(minWidth: value, maxWidth: value, maxHeight: .infinity)
        } else {
            view.frame(maxWidth: .infinity, minHeight: value, maxHeight: value)
        }
    }

    /// Resolve every child's on-screen extent for a stack of `total` points along its axis: a fixed
    /// child's own points, or (fraction × total) for a proportional one — `storedOverrides` (a
    /// previously seeded or dragged resizable column) substitutes for the fraction at that index
    /// when present. The SUM of every sized (fixed + fraction) child is then bounded to leave at
    /// least `flexMinimum` for whatever flexes, scaling every sized child down proportionally if
    /// needed but never below `minPerPane` — this is what stops two 360pt-equivalent children
    /// summing to more than a 600pt stack (#4688), and replaces the old single-value `clamp` that
    /// also wrongly passed the raw value through whenever `total <= 96`.
    ///
    /// Pure — no SwiftUI, no view mounting. `WorkspaceSplitStackTests` calls this directly at
    /// several stack sizes.
    static func resolvedExtents(
        _ sizings: [Sizing],
        storedOverrides: [Double?] = [],
        total: Double,
        minPerPane: Double = 48,
        flexMinimum: Double = 48
    ) -> [Double?] {
        guard total > 0 else { return sizings.map { _ in nil } }
        let requested: [Double?] = sizings.enumerated().map { index, sizing in
            switch sizing {
            case .flex:
                return nil
            case let .fixed(points):
                return points
            case let .fraction(fraction):
                if index < storedOverrides.count, let stored = storedOverrides[index] { return stored }
                return fraction * total
            }
        }
        let sizedValues = requested.compactMap { $0 }
        guard !sizedValues.isEmpty else { return requested }
        let rawSum = sizedValues.reduce(0, +)
        // Never bound below every pane's own minimum, or the clamp would fight itself.
        let minSum = Double(sizedValues.count) * minPerPane
        let budget = max(minSum, total - flexMinimum)
        let scale = rawSum > budget ? budget / rawSum : 1.0
        return requested.map { value in
            guard let value else { return nil }
            return max(minPerPane, value * scale)
        }
    }

    private func divider(_ extent: Binding<Double>, edge: ResizableDivider.Edge, total: CGFloat) -> some View {
        ResizableDivider(
            width: extent,
            minWidth: 48,
            maxWidth: max(96, Double(total) - 48),
            edge: edge,
            axis: axis == .horizontal ? .horizontal : .vertical
        )
    }
}

// MARK: - Previews

/// A stand-in pane. Real panes are AppKit-backed; a coloured block renders the SAME
/// layout question (does each child get a bounded proposal?) without an engine.
private func previewPane(_ label: String, _ tint: Color) -> AnyView {
    AnyView(
        tint.opacity(0.22)
            .overlay(Text(label).font(.caption).foregroundStyle(.secondary))
    )
}

#Preview("Horizontal — proportional library + flexing content") {
    WorkspaceSplitStack(
        axis: .horizontal,
        storageKey: "preview.horizontal",
        children: [
            .init(previewPane("Library", .blue), sizing: .fraction(0.4)),
            .init(previewPane("Reader", .green))
        ]
    )
    .frame(width: 900, height: 500)
}

#Preview("Film strip — 72pt library under the content") {
    WorkspaceSplitStack(
        axis: .vertical,
        storageKey: "preview.filmstrip",
        children: [
            .init(previewPane("Transcribe", .green)),
            .init(previewPane("Film strip", .orange), sizing: .fixed(72))
        ]
    )
    .frame(width: 900, height: 500)
}

// The crash case (CD, 2026-09-16): a stack NESTED inside another stack is what fed an
// unbounded proposal into the AppKit panes and sent `_layoutSubtreeWithOldSize:` into
// infinite recursion. If the one-frame-per-child rule ever regresses, this preview is
// where it shows up first — cheaply, without launching the app.
#Preview("Nested — compare over a film strip") {
    WorkspaceSplitStack(
        axis: .vertical,
        storageKey: "preview.nested.outer",
        children: [
            .init(AnyView(
                WorkspaceSplitStack(
                    axis: .horizontal,
                    storageKey: "preview.nested.inner",
                    children: [
                        .init(previewPane("Page A", .blue), sizing: .fraction(0.4)),
                        .init(previewPane("Page B", .purple))
                    ]
                )
            )),
            .init(previewPane("Film strip", .orange), sizing: .fixed(72))
        ]
    )
    .frame(width: 900, height: 500)
}
