import SwiftUI

/// A RESIZABLE stack for an applied workspace's splits. Lays 1–N child panes out along `axis`.
///
/// Each child is FLEX (fills the remainder), a DEFAULT EXTENT (`Sizing.fixed`, absolute points —
/// the film strip, which does not SCALE with the display but IS draggable, floored at its own
/// configured value — #4876/#4848, source-model panes recon slice D, 2026-09-20: "a default, not
/// a pin", replacing the earlier "never resizable, no divider" behavior of the same name), or
/// PROPORTIONAL (`Sizing.fraction`, a share of the stack's own extent, resizable via a
/// `ResizableDivider` once dragged) (#4688, CD 2026-09-17: "think through % ... for the various
/// default workspaces").
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
        /// A DEFAULT extent, absolute points, resizable (slice D, 2026-09-20 — was a hard,
        /// never-resizable pin; #4876/#4848). The UNDRAGGED value is exactly this many points —
        /// it does not scale with `total` the way `.fraction` does, so "the strip of page icons
        /// should not grow with the display" (CD 2026-09-16) still holds by default — but a drag
        /// now persists over it (same id-keyed store `.fraction` uses, storing raw points here
        /// instead of a 0...1 share — see `storedOverrides`), floored at this same value: the
        /// strip can grow, never shrink below its own configured minimum.
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

    /// One child of the stack. `id` is REQUIRED, not defaulted (2026-09-20, slice B/C: identity
    /// by pane id, not array position) — a silent default would make "forgot to pass the real
    /// pane id" compile clean and fail only at runtime, the exact class of bug this change
    /// exists to close. Production call sites (`ContentView.paneListRow`/`.paneSplitView`) pass
    /// `PaneNode.id` — stable for a leaf OR a split (both cases of `PaneNode.id`,
    /// `PaneList.swift:147-152`); a split node's own id is deterministic for built-in workspaces
    /// (`UUID(stableName:)`) and, for a runtime-created split, lives IN `activePaneList` and so
    /// stays fixed across re-renders until the model itself changes it — either way it is a
    /// value the MODEL owns, never re-derived from tree position. `#Preview` blocks below pass a
    /// fresh literal id inline; they render once and never reshuffle, so identity stability
    /// doesn't matter there.
    struct Child {
        let id: UUID
        let view: AnyView
        let sizing: Sizing

        init(_ view: AnyView, id: UUID, sizing: Sizing = .flex) {
            self.id = id
            self.view = view
            self.sizing = sizing
        }
    }

    let axis: SplitAxis
    let children: [Child]

    /// Per-pane-id fractions (0...1) of the stack's own extent, for every RESIZABLE
    /// (`.fraction`) child — replaces the three positional `extent0/1/2` slots (#4972, source-
    /// model panes recon slice C, 2026-09-20): a value keyed by ARRAY POSITION silently
    /// reattached to whichever pane now occupies that slot after a close, leaving the closed
    /// pane's old width as a gap and the survivors never growing into it. Keyed by `Child.id`
    /// instead: a closed pane's id is simply never looked up again (nothing prunes the JSON
    /// entry, nothing needs to — `storedOverrides` only ever reads the CURRENT children's own
    /// ids). The survivors grow into the freed space because `PaneSpec.childSizings` always leaves
    /// one FLEXING pane, which absorbs it — stored values are never rescaled (#5014). A single
    /// JSON-encoded string, not a per-id `@SceneStorage`
    /// property (which needs FIXED properties, per the old three-slot comment this replaces) —
    /// this is why it can hold any number of ids without another #4849-style slot cap.
    ///
    /// Stored as FRACTIONS, not the old absolute points: a fraction naturally re-scales with
    /// `total` (a window resize); an absolute point value would not.
    ///
    /// A DIFFERENT `@SceneStorage` key name than the old `"wsplit.<key>.0/1/2"` (`"wsplit.<key>.
    /// fractions"` — see `init`), where `<key>` is the split's tree position alone (`storageKey`,
    /// #4994) — old positional values are simply never read into this path,
    /// same as slice A's "stale keys must be harmless" rule: a pre-migration window resets ONCE,
    /// landing on the workspace's own DEFAULT proportions (Browse still opens 15/60/25), not on
    /// equal thirds — `storedOverrides` returns `nil` for every id absent from a fresh `"{}"`,
    /// and `resolvedExtents`'s existing `nil` fallback is `fraction * total`, i.e. each child's
    /// own configured default share.
    @SceneStorage private var storedFractionsJSON: String

    init(axis: SplitAxis, storageKey: String, children: [Child]) {
        self.axis = axis
        self.children = children
        self._storedFractionsJSON = SceneStorage(wrappedValue: "{}", "wsplit.\(storageKey).fractions")
    }

    /// The storage-key component: the split's tree POSITION ("root", "0", "0.1", …) and nothing
    /// else (#4994). A position is fixed for the life of the view that sits at it, which is what
    /// `@SceneStorage` requires — its key is read ONCE, when the view is first installed.
    ///
    /// This used to append the leading child's pane id (#4688), so that Read's inner split and
    /// Transcribe's film strip — both at position "0" — did not share one slot of positional
    /// extents. But the stack at a position keeps its SwiftUI identity when a different
    /// workspace is applied (or its leading pane is split or closed) while that id changes, so
    /// the key changed under a live view: SwiftUI kept the first key, logged "SceneStorage may
    /// not change its key after initialization" on every later render, and wrote every drag
    /// into the FIRST workspace's slot. #4688's purpose — a size never leaks between workspaces
    /// — is now served INSIDE the value: the stored JSON is keyed by pane id
    /// (`storedFractionsJSON`), the five built-in workspaces' ids are deterministic and pairwise
    /// disjoint, and a runtime-created pane mints a fresh id. `WorkspaceSplitStackSizingTests`
    /// pins both halves.
    // #4902: `nonisolated` is load-bearing, not decorative — WorkspaceSplitStackSizingTests
    // is a non-@MainActor Swift Testing suite that calls this directly; a View's static
    // members are @MainActor-isolated by default (Swift 6), so without this the call would
    // not even compile off-main. Pure string composition, no actor-isolated state read.
    nonisolated static func storageKey(keyPath: String) -> String {
        keyPath
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

    /// Decode the stored per-id fractions. Malformed/empty JSON decodes to an empty map — never
    /// throws, never crashes the layout on a corrupted default (the same "read back what
    /// actually landed" discipline the rest of this file follows for @SceneStorage sentinels).
    /// An unrecognised/malformed key (not a `UUID`) is silently ignored, never crashed on.
    ///
    /// Pure, `nonisolated`, directly unit-testable without a view or a real `@SceneStorage`
    /// (which needs a hosting scene to persist at all) — this is the encode/decode LOGIC only;
    /// `storedFractionsById()`/`writeStoredFraction(_:for:)` below are the thin instance-side
    /// wrappers that actually read/write `storedFractionsJSON`.
    nonisolated static func decodeStoredFractions(_ json: String) -> [UUID: Double] {
        guard let data = json.data(using: .utf8),
              let raw = try? JSONDecoder().decode([String: Double].self, from: data)
        else { return [:] }
        var out: [UUID: Double] = [:]
        for (key, value) in raw {
            guard let id = UUID(uuidString: key) else { continue }
            out[id] = value
        }
        return out
    }

    /// The inverse of `decodeStoredFractions` — `nil` (never a crash) if encoding somehow fails.
    nonisolated static func encodeStoredFractions(_ fractions: [UUID: Double]) -> String? {
        var raw: [String: Double] = [:]
        for (id, value) in fractions { raw[id.uuidString] = value }
        guard let data = try? JSONEncoder().encode(raw) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func storedFractionsById() -> [UUID: Double] {
        Self.decodeStoredFractions(storedFractionsJSON)
    }

    /// Persist ONE child's dragged fraction by its pane id, leaving every other stored id
    /// untouched (including one for a pane not currently in `children` — a pane that closes and
    /// later reopens with the SAME id, e.g. undo, gets its old width back; nothing here ever
    /// prunes an id, since nothing needs to: a closed pane's id is simply never looked up again).
    private func writeStoredFraction(_ fraction: Double, for id: UUID) {
        var current = storedFractionsById()
        current[id] = fraction
        guard let json = Self.encodeStoredFractions(current) else { return }
        storedFractionsJSON = json
    }

    /// The resolved value for a `.fixed` (default-extent) child: its own stored drag if present,
    /// floored at its configured default — a drag can grow the strip, never shrink it below the
    /// size its workspace defines (slice D, 2026-09-20, #4876/#4848). `nil` (never dragged) tells
    /// the caller to fall back to `points` itself. Independent of any sibling: closing one can never disturb it.
    ///
    /// Pure, `nonisolated`, directly unit-testable without a view.
    nonisolated static func resolvedFixedExtent(default points: Double, stored: Double?) -> Double? {
        guard let stored else { return nil }
        return max(points, stored)
    }

    /// The stored override for each RESIZABLE child (`.fraction` or `.fixed`), in child order,
    /// as ABSOLUTE POINTS (`resolvedExtents`'s contract) — `nil` for a child never dragged (it
    /// falls back to its own default) and for `.flex` (which stores nothing).
    ///
    /// One id-keyed store holds both kinds; the NUMBER means something different for each: for
    /// `.fraction` a 0...1 share of the stack, for `.fixed` absolute points floored at the
    /// child's configured default.
    ///
    /// A stored value is what the person dragged, and it is used AS IT IS (#5014). An earlier
    /// version rescaled the stored fractions on every pass so that together they summed to their
    /// defaults: a lone dragged pane was scaled straight back to its default (its divider looked
    /// dead, #5012), and two dragged panes could only trade with EACH OTHER, so dragging the
    /// right divider moved the left pane. A divider trades space between the pane it sizes and
    /// the flexing pane, nothing else; `resolvedExtents`' sum-clamp keeps the row fitting, and
    /// `PaneSpec.childSizings` guarantees a flexing pane so a close never leaves a gap.
    ///
    /// Pure, `nonisolated`, directly unit-testable without a view.
    nonisolated static func storedOverrides(
        sizings: [Sizing], ids: [UUID], storedById: [UUID: Double], total: Double
    ) -> [Double?] {
        guard sizings.count == ids.count else { return sizings.map { _ in nil } }
        return sizings.indices.map { index in
            switch sizings[index] {
            case .fraction:
                return storedById[ids[index]].map { $0 * total }
            case let .fixed(points):
                return resolvedFixedExtent(default: points, stored: storedById[ids[index]])
            case .flex:
                return nil
            }
        }
    }

    private func storedOverrides(total: Double) -> [Double?] {
        Self.storedOverrides(
            sizings: children.map(\.sizing), ids: children.map(\.id),
            storedById: storedFractionsById(), total: total
        )
    }

    /// The children interleaved with dividers. A divider sits between a resizable child and the
    /// flexing content, on the side facing the flex, so dragging it resizes the resizable pane.
    /// Resizable children BEFORE the flex get the divider after them (drag toward trailing to
    /// grow); one AFTER the flex (a trailing strip) gets the divider before it (drag toward
    /// leading to grow). Slice D, 2026-09-20 (#4876/#4848): a `.fixed` child now gets one too —
    /// it is RESIZABLE (default extent, floored at its own value), not exempt.
    @ViewBuilder private func arranged(total: CGFloat) -> some View {
        let resolved = Self.resolvedExtents(
            children.map(\.sizing), storedOverrides: storedOverrides(total: Double(total)), total: Double(total)
        )
        let flexIndex = children.firstIndex { child in
            if case .flex = child.sizing { return true }
            return false
        } ?? max(0, children.count - 1)

        let plans: [ChildPlan] = children.enumerated().map { index, child in
            switch child.sizing {
            case .flex:
                return ChildPlan(id: child.id, view: child.view, layout: .flex)
            case let .fixed(points):
                // Slice D: writes RAW POINTS (`newValue`, no `/total`) — `.fixed`'s stored value
                // is absolute, unlike `.fraction`'s 0...1 share (see `storedOverrides` above).
                // Floored at `points` via `divider`'s own `minWidth:` below, so a drag can never
                // shrink the strip past its configured default.
                let displayValue = resolved[index] ?? points
                let childId = child.id
                let binding = Binding<Double>(
                    get: { displayValue },
                    set: { newValue in writeStoredFraction(newValue, for: childId) }
                )
                return ChildPlan(
                    id: child.id, view: child.view,
                    layout: .resizable(binding, display: displayValue, dividerBefore: index > flexIndex, minWidth: points)
                )
            case .fraction:
                // SF3 review finding: this used to be a plain pass-through to a raw @SceneStorage
                // slot, which is WHY something had to seed it with an absolute-points value before
                // the divider had anything sane to show or drag from. A COMPUTED binding instead:
                // its getter is the already-resolved display value (the fraction of `total` until
                // a real drag has written a stored override, per `resolvedExtents`/`storedOverrides`
                // above), so nothing is ever seeded — the fraction re-resolves fresh against
                // whatever `total` is THIS render. The setter is the only path that ever writes
                // `storedFractionsJSON`, and it only fires from `ResizableDivider`'s own drag
                // handler — never from a mere appearance. Writes a FRACTION (`newValue / total`),
                // keyed by THIS child's own id (slice C, 2026-09-20) — never a position.
                let displayValue = resolved[index] ?? 0
                let childId = child.id
                let stackTotal = Double(total)
                let binding = Binding<Double>(
                    get: { displayValue },
                    set: { newValue in
                        guard stackTotal > 0 else { return }
                        writeStoredFraction(newValue / stackTotal, for: childId)
                    }
                )
                return ChildPlan(
                    id: child.id, view: child.view,
                    layout: .resizable(binding, display: displayValue, dividerBefore: index > flexIndex, minWidth: 48)
                )
            }
        }
        ForEach(plans, id: \.id) { plan in
            switch plan.layout {
            case .flex:
                plan.view.frame(maxWidth: .infinity, maxHeight: .infinity)
            case let .resizable(binding, display, dividerBefore, minWidth):
                if dividerBefore { divider(binding, edge: .trailing, total: total, minWidth: minWidth) }
                sized(plan.view, value: display)
                if !dividerBefore { divider(binding, edge: .leading, total: total, minWidth: minWidth) }
            }
        }
    }

    /// How one child is laid out this render: filling the remainder, or resizable — bound to a
    /// stored value, displayed at its resolved (clamped) extent, with a divider on the side
    /// facing the flex, floored at `minWidth` (its own default extent for `.fixed`, the generic
    /// `48` for `.fraction`). Slice D, 2026-09-20: a separate `.fixed` case (no divider, ever) is
    /// GONE — `.fixed` now renders through this same resizable path, since it IS resizable.
    /// Sibling of `ChildPlan`, not nested inside it — three levels of nesting
    /// (stack > plan > layout) buys nothing and trips `nesting`.
    private enum ChildLayout {
        case flex
        case resizable(Binding<Double>, display: Double, dividerBefore: Bool, minWidth: Double)
    }

    private struct ChildPlan {
        let id: UUID
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

    /// Resolve every child's on-screen extent for a stack of `total` points along its axis: a
    /// fixed child's own DEFAULT points, or (fraction × total) for a proportional one —
    /// `storedOverrides` (a previously dragged resizable column, `.fixed` OR `.fraction` since
    /// slice D, 2026-09-20) substitutes at that index when present. The SUM of every sized
    /// (fixed + fraction) child is then bounded to leave at
    /// least `flexMinimum` for whatever flexes, scaling every sized child down proportionally if
    /// needed but never below `minPerPane` — this is what stops two 360pt-equivalent children
    /// summing to more than a 600pt stack (#4688), and replaces the old single-value `clamp` that
    /// also wrongly passed the raw value through whenever `total <= 96`.
    ///
    /// Pure — no SwiftUI, no view mounting. `WorkspaceSplitStackTests` calls this directly at
    /// several stack sizes.
    // #4902: `nonisolated` is load-bearing — WorkspaceSplitStackSeedingTests
    // and WorkspaceSplitStackSizingTests are non-@MainActor Swift Testing
    // suites calling this directly; pure over its own parameters, no
    // actor-isolated state read.
    nonisolated static func resolvedExtents(
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
                // Slice D, 2026-09-20 (#4876/#4848): `.fixed` is resizable now, so it reads a
                // stored override exactly like `.fraction` does — `points` is only the DEFAULT,
                // never dragged.
                if index < storedOverrides.count, let stored = storedOverrides[index] { return stored }
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

    /// `minWidth` floors the drag — `48` for a `.fraction` column (unchanged), or a `.fixed`
    /// child's own configured default extent (slice D, 2026-09-20): the strip can grow, never
    /// shrink below the size its workspace defines.
    private func divider(
        _ extent: Binding<Double>, edge: ResizableDivider.Edge, total: CGFloat, minWidth: Double = 48
    ) -> some View {
        ResizableDivider(
            width: extent,
            minWidth: minWidth,
            maxWidth: max(minWidth + 48, Double(total) - 48),
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
            .init(previewPane("Library", .blue), id: UUID(), sizing: .fraction(0.4)),
            .init(previewPane("Reader", .green), id: UUID())
        ]
    )
    .frame(width: 900, height: 500)
}

#Preview("Film strip — 72pt library under the content") {
    WorkspaceSplitStack(
        axis: .vertical,
        storageKey: "preview.filmstrip",
        children: [
            .init(previewPane("Transcribe", .green), id: UUID()),
            .init(previewPane("Film strip", .orange), id: UUID(), sizing: .fixed(72))
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
                        .init(previewPane("Page A", .blue), id: UUID(), sizing: .fraction(0.4)),
                        .init(previewPane("Page B", .purple), id: UUID())
                    ]
                )
            ), id: UUID()),
            .init(previewPane("Film strip", .orange), id: UUID(), sizing: .fixed(72))
        ]
    )
    .frame(width: 900, height: 500)
}
