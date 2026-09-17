import SwiftUI

/// A RESIZABLE stack for an applied workspace's splits. Lays 1–N child panes out along `axis`.
///
/// Each child is either SIZED — a default extent along the axis, resizable via a `ResizableDivider`
/// (the resizable columns) — or FLEXING (`extent == nil`), which fills the remainder. A film-strip
/// pane passes a small extent (e.g. 72) so the library strip stays narrow while the content flexes
/// (CD 2026-09-16: "the strip should be very narrow, like a film script").
///
/// EVERYTHING is wrapped in a `GeometryReader` and every extent is CLAMPED to the available space —
/// the pattern `SplittablePane` uses. The previous version stacked TWO frames on each fixed child
/// (`.frame(width: fixed).frame(maxHeight: .infinity)`); when a stack was NESTED inside another, that
/// fed an unbounded size proposal into the AppKit-backed panes and AppKit's `_layoutSubtreeWithOldSize:`
/// never converged → the infinite-layout-recursion crash the CD hit (2026-09-16). One frame per child,
/// clamped, no `fixed → .infinity` pair.
struct WorkspaceSplitStack: View {
    /// One child of the stack. `extent == nil` ⇒ this pane FLEXES; a non-nil extent is the default
    /// resizable size along the axis (small for a film strip).
    struct Child {
        let view: AnyView
        let extent: Double?

        init(_ view: AnyView, extent: Double? = nil) {
            self.view = view
            self.extent = extent
        }
    }

    let axis: SplitAxis
    let children: [Child]

    // Up to two SIZED child slots persist their extent per split position. Every built-in split has
    // at most two sized children (the third pane, if any, flexes), so two slots suffice.
    // ponytail: two @SceneStorage slots, not an array — @SceneStorage needs fixed properties; a
    // 3rd sized child would reuse slot 1 (never happens in the five built-ins).
    @SceneStorage private var extent0: Double
    @SceneStorage private var extent1: Double

    init(axis: SplitAxis, storageKey: String, children: [Child]) {
        self.axis = axis
        self.children = children
        let sized = children.compactMap(\.extent)
        let fallback: Double = axis == .horizontal ? 360 : 300
        self._extent0 = SceneStorage(wrappedValue: sized.first ?? fallback, "wsplit.\(storageKey).0")
        self._extent1 = SceneStorage(wrappedValue: sized.dropFirst().first ?? fallback, "wsplit.\(storageKey).1")
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

    /// The children interleaved with dividers. A divider sits between a SIZED child and the flexing
    /// content, on the side facing the flex, so dragging it resizes the sized pane. Sized children
    /// BEFORE the flex get the divider after them (drag toward trailing to grow); a sized child
    /// AFTER the flex (a trailing strip) gets the divider before it (drag toward leading to grow).
    @ViewBuilder private func arranged(total: CGFloat) -> some View {
        let flexIndex = children.firstIndex { $0.extent == nil } ?? max(0, children.count - 1)
        // Assign the two stored slots to sized children in order.
        var slot = 0
        let plans: [ChildPlan] = children.enumerated().map { index, child in
            if child.extent == nil {
                return ChildPlan(view: child.view, sizing: .flex)
            }
            let binding = slot == 0 ? $extent0 : $extent1
            slot += 1
            return ChildPlan(view: child.view, sizing: .sized(binding, dividerBefore: index > flexIndex))
        }
        ForEach(Array(plans.enumerated()), id: \.offset) { _, plan in
            switch plan.sizing {
            case .flex:
                plan.view.frame(maxWidth: .infinity, maxHeight: .infinity)
            case let .sized(binding, dividerBefore):
                // A sized child BEFORE the flex is the leading panel (drag its trailing divider to
                // grow); a sized strip AFTER the flex is the trailing panel (drag its leading divider).
                if dividerBefore { divider(binding, edge: .trailing, total: total) }
                sized(plan.view, binding, total: total)
                if !dividerBefore { divider(binding, edge: .leading, total: total) }
            }
        }
    }

    /// How one child is laid out: filling the remainder, or pinned to a stored
    /// extent with a divider on the side facing the flex.
    /// Sibling of `ChildPlan`, not nested inside it — three levels of nesting
    /// (stack > plan > sizing) buys nothing and trips `nesting`.
    private enum ChildSizing {
        case flex
        case sized(Binding<Double>, dividerBefore: Bool)
    }

    private struct ChildPlan {
        let view: AnyView
        let sizing: ChildSizing
    }

    /// A sized child, clamped to the available space so it can never propose an unbounded/over-large
    /// size into its AppKit content (the crash guard). ONE frame — the fixed axis is set, the cross
    /// axis fills; no stacked `fixed → .infinity` pair.
    @ViewBuilder private func sized(_ view: AnyView, _ extent: Binding<Double>, total: CGFloat) -> some View {
        let value = clamp(extent.wrappedValue, total: total)
        // ONE frame node: pin the axis via min == max, flex the cross axis. (`.frame(width:maxHeight:)`
        // mixes two frame overloads and won't compile; the stacked `.frame(width:).frame(maxHeight:)`
        // pair is the one that fed the unbounded proposal into AppKit and crashed. This is neither.)
        if axis == .horizontal {
            view.frame(minWidth: value, maxWidth: value, maxHeight: .infinity)
        } else {
            view.frame(maxWidth: .infinity, minHeight: value, maxHeight: value)
        }
    }

    /// Clamp an extent to [48, total − 48] so neither side collapses and nothing exceeds the stack.
    private func clamp(_ value: Double, total: CGFloat) -> Double {
        guard total > 96 else { return value }
        return min(max(value, 48), Double(total) - 48)
    }

    private func divider(_ extent: Binding<Double>, edge: ResizableDivider.Edge, total: CGFloat) -> some View {
        ResizableDivider(
            width: extent,
            minWidth: axis == .horizontal ? 48 : 48,
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

#Preview("Horizontal — sized library + flexing content") {
    WorkspaceSplitStack(
        axis: .horizontal,
        storageKey: "preview.horizontal",
        children: [
            .init(previewPane("Library", .blue), extent: 360),
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
            .init(previewPane("Film strip", .orange), extent: 72)
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
                        .init(previewPane("Page A", .blue), extent: 360),
                        .init(previewPane("Page B", .purple))
                    ]
                )
            )),
            .init(previewPane("Film strip", .orange), extent: 72)
        ]
    )
    .frame(width: 900, height: 500)
}
