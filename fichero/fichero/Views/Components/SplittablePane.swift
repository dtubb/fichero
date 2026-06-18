import SwiftUI

// MARK: - Environment: split controls (consumed by MiniToolbar)

/// Injected by SplittablePane so MiniToolbar can render the split buttons
/// inside its own bar rather than requiring a separate top bar.
struct SplitAxisActions: @unchecked Sendable {
    let hasVertical: Bool
    let hasHorizontal: Bool
    let onToggleVertical: () -> Void
    let onToggleHorizontal: () -> Void
}

private struct SplitAxisActionsKey: EnvironmentKey {
    static let defaultValue: SplitAxisActions? = nil
}

extension EnvironmentValues {
    var splitAxisActions: SplitAxisActions? {
        get { self[SplitAxisActionsKey.self] }
        set { self[SplitAxisActionsKey.self] = newValue }
    }
}

// MARK: - Environment: secondary pane flag

/// `true` for every pane that is NOT the primary (top-left / first) instance
/// when a SplittablePane is split. Secondary panes MUST NOT register duplicate
/// NSToolbar items — e.g. `.searchable(placement: .toolbar)` crashes the
/// toolbar subsystem when two views in the same window register the same item.
private struct IsSecondarySplitPaneKey: EnvironmentKey {
    static let defaultValue: Bool = false
}

extension EnvironmentValues {
    /// When `true`, the view is a non-primary copy inside a split pane.
    /// Views that contribute NSToolbar items (`.searchable`, custom
    /// `ToolbarItem`s with fixed identifiers) should skip those contributions
    /// to prevent NSToolbar duplicate-identifier crashes.
    var isSecondarySplitPane: Bool {
        get { self[IsSecondarySplitPaneKey.self] }
        set { self[IsSecondarySplitPaneKey.self] = newValue }
    }
}

// MARK: - SplittablePane

/// Wraps a content pane so the user can independently split it left/right and
/// top/bottom per column.
///
/// **Split controls** surface inside the pane's own `MiniToolbar` via the
/// `splitAxisActions` environment value — no separate bar is added on top.
///
/// **Independent column splits:**
/// - V button toggles left/right split for the whole pane.
/// - H button toggles top/bottom for the *specific column* the button lives in.
///   Left and right columns can each be split horizontally on their own,
///   so you can reach 1, 2, or 3 panes without being forced to a full 2×2.
///
/// **NSToolbar safety:** The vertical split uses `HStack + ResizableDivider`
/// rather than `HSplitView` (NSSplitView) so the column separator does NOT
/// extend into the window title bar and make NSToolbar appear split.
///
/// **Secondary panes:** every half that is NOT the top-left primary receives
/// `isSecondarySplitPane = true` in its environment so `.searchable()` and
/// other unique NSToolbar registrations are suppressed.
struct SplittablePane<Content: View>: View {
    private let storageKey: String
    private let content: () -> Content

    /// Left/right split — shared across all columns.
    @SceneStorage private var hasVertical: Bool
    /// Top/bottom split for the primary (left, or only) column.
    @SceneStorage private var primaryHasHorizontal: Bool
    /// Top/bottom split for the secondary (right) column. Irrelevant when
    /// `hasVertical` is false.
    @SceneStorage private var secondaryHasHorizontal: Bool
    /// Width of the primary (left) pane when the vertical split is active.
    /// Persisted so the divider position survives window re-opens.
    @SceneStorage private var verticalSplitLeftWidth: Double

    /// - Parameters:
    ///   - storageKey: Stable per-pane key ("library", "canvas", "reading").
    ///     Used to namespace `@SceneStorage` so each pane's split state is
    ///     independent within the same window.
    ///   - content: The pane's view factory, rendered once or multiple times
    ///     depending on the active split configuration.
    init(storageKey: String, @ViewBuilder content: @escaping () -> Content) {
        self.storageKey = storageKey
        self.content = content
        self._hasVertical = SceneStorage(wrappedValue: false, "splittablePane.\(storageKey).v")
        self._primaryHasHorizontal = SceneStorage(wrappedValue: false, "splittablePane.\(storageKey).ph")
        self._secondaryHasHorizontal = SceneStorage(wrappedValue: false, "splittablePane.\(storageKey).sh")
        self._verticalSplitLeftWidth = SceneStorage(wrappedValue: 400, "splittablePane.\(storageKey).vsw")
    }

    var body: some View {
        splitContainer
    }

    // MARK: Toggle logic

    private func toggleVertical() {
        hasVertical.toggle()
        // Discard the secondary column's H-split state when collapsing V.
        if !hasVertical { secondaryHasHorizontal = false }
    }

    private func togglePrimaryHorizontal() { primaryHasHorizontal.toggle() }
    private func toggleSecondaryHorizontal() { secondaryHasHorizontal.toggle() }

    // MARK: Split container

    @ViewBuilder
    private var splitContainer: some View {
        if hasVertical {
            // HStack + ResizableDivider instead of HSplitView so the divider
            // does NOT bleed into the window title bar (an NSSplitView quirk
            // that makes NSToolbar appear visually split alongside the content).
            //
            // GeometryReader clamps leftWidth so it can never exceed
            // (available - minSecondary - divider), preventing NSConstraintLoop
            // crashes from over-constrained fixed-width frames (#2317).
            GeometryReader { proxy in
                let available = proxy.size.width > 0
                    ? Double(proxy.size.width)
                    : verticalSplitLeftWidth + 248   // 240 min-secondary + 8 divider
                let maxLeft = max(240, available - 248)
                let leftWidth = CGFloat(max(240, min(verticalSplitLeftWidth, maxLeft)))
                HStack(spacing: 0) {
                    primaryColumn
                        .frame(width: leftWidth)
                        .environment(\.splitAxisActions, SplitAxisActions(
                            hasVertical: true,
                            hasHorizontal: primaryHasHorizontal,
                            onToggleVertical: toggleVertical,
                            onToggleHorizontal: togglePrimaryHorizontal
                        ))
                    ResizableDivider(
                        width: $verticalSplitLeftWidth,
                        minWidth: 240,
                        maxWidth: min(900, maxLeft),
                        edge: .leading
                    )
                    secondaryColumn
                        .frame(minWidth: 240, maxWidth: .infinity)
                        .environment(\.splitAxisActions, SplitAxisActions(
                            hasVertical: true,
                            hasHorizontal: secondaryHasHorizontal,
                            onToggleVertical: toggleVertical,
                            onToggleHorizontal: toggleSecondaryHorizontal
                        ))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if primaryHasHorizontal {
            // Top / Bottom (no V-split). VSplitView dividers are horizontal and
            // do not extend into the title bar, so it's safe to keep here.
            VSplitView {
                content()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
                    .environment(\.splitAxisActions, SplitAxisActions(
                        hasVertical: false,
                        hasHorizontal: true,
                        onToggleVertical: toggleVertical,
                        onToggleHorizontal: togglePrimaryHorizontal
                    ))
                secondary()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
                    .environment(\.splitAxisActions, SplitAxisActions(
                        hasVertical: false,
                        hasHorizontal: true,
                        onToggleVertical: toggleVertical,
                        onToggleHorizontal: togglePrimaryHorizontal
                    ))
            }
        } else {
            // Single pane — no split.
            content()
                .environment(\.splitAxisActions, SplitAxisActions(
                    hasVertical: false,
                    hasHorizontal: false,
                    onToggleVertical: toggleVertical,
                    onToggleHorizontal: togglePrimaryHorizontal
                ))
        }
    }

    // MARK: Column helpers

    /// Primary (left, or only) column — optionally split top/bottom.
    @ViewBuilder
    private var primaryColumn: some View {
        if primaryHasHorizontal {
            VSplitView {
                content()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
                secondary()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
            }
        } else {
            content()
        }
    }

    /// Secondary (right) column — optionally split top/bottom.
    @ViewBuilder
    private var secondaryColumn: some View {
        if secondaryHasHorizontal {
            VSplitView {
                secondary()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
                secondary()
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: .infinity)
            }
        } else {
            secondary()
        }
    }

    /// A secondary copy of `content()` with `isSecondarySplitPane = true`
    /// so that views suppress duplicate NSToolbar registrations.
    private func secondary() -> some View {
        content().environment(\.isSecondarySplitPane, true)
    }
}
