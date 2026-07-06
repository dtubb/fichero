import SwiftUI

// MARK: - Environment: split controls (consumed by MiniToolbar)

/// Injected by SplittablePane so MiniToolbar can render the split buttons
/// inside its own bar rather than requiring a separate top bar.
struct SplitAxisActions: @unchecked Sendable {
    let hasVertical: Bool
    let hasHorizontal: Bool
    let paneCount: Int
    let onToggleVertical: () -> Void
    let onToggleHorizontal: () -> Void
    let onCollapseSplit: () -> Void
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

// MARK: - Toolbar search registration policy (#1447/#2309)

/// Single source of truth for "may this pane register the toolbar search item?".
/// Only the *primary* pane may register `.searchable(placement: .toolbar)`; a
/// secondary split-pane copy registering the same fixed NSToolbar identifier
/// crashes the toolbar subsystem with a duplicate-identifier error. Every
/// mode-specific view that owns the toolbar search slot (LibraryView, SearchView)
/// gates its `.searchable` and search `.onSubmit` through this predicate so the
/// invariant lives in one testable place instead of being re-inlined per view.
enum ToolbarSearchRegistration {
    static func shouldRegister(isSecondarySplitPane: Bool) -> Bool {
        !isSecondarySplitPane
    }
}

struct SplitPaneState {
    var verticalPaneCount: Int = 1
    var horizontalPaneCount: Int = 1

    var hasVertical: Bool { verticalPaneCount > 1 }
    var hasHorizontal: Bool { horizontalPaneCount > 1 }

    var paneCount: Int {
        max(verticalPaneCount, horizontalPaneCount)
    }

    mutating func toggleVertical() {
        horizontalPaneCount = 1
        verticalPaneCount = cyclePaneCount(verticalPaneCount)
    }

    mutating func toggleHorizontal() {
        verticalPaneCount = 1
        horizontalPaneCount = cyclePaneCount(horizontalPaneCount)
    }

    mutating func collapseOnePane() {
        if verticalPaneCount > 1 {
            verticalPaneCount -= 1
            return
        }
        if horizontalPaneCount > 1 {
            horizontalPaneCount -= 1
        }
    }

    private func cyclePaneCount(_ count: Int) -> Int {
        switch count {
        case 1: return 2
        case 2: return 3
        default: return 1
        }
    }
}

// MARK: - SplittablePane

/// Wraps a content pane so the user can independently split it left/right and
/// top/bottom per column.
///
/// **Split controls** surface inside the pane's own `MiniToolbar` via the
/// `splitAxisActions` environment value - no separate bar is added on top.
///
/// **Bounded split counts:**
/// - each axis cycles through 1, 2, and 3 panes
/// - closing any pane collapses the active axis back one step at a time
/// - secondary panes continue to receive `isSecondarySplitPane = true` so
///   toolbar registrations stay unique
///
/// **NSToolbar safety:** the divider lives in the content area and does not
/// extend into the title bar, so toolbar chrome stays intact.
struct SplittablePane<Content: View>: View {
    private let storageKey: String
    private let content: () -> Content

    /// Number of panes in the active left/right layout.
    @SceneStorage private var verticalPaneCount: Int
    /// Number of panes in the active top/bottom layout.
    @SceneStorage private var horizontalPaneCount: Int
    /// Width of the first pane in a 2- or 3-column vertical layout.
    @SceneStorage private var verticalPrimaryExtent: Double
    /// Width of the middle pane in a 3-column vertical layout.
    @SceneStorage private var verticalSecondaryExtent: Double
    /// Height of the first pane in a 2- or 3-row horizontal layout.
    @SceneStorage private var horizontalPrimaryExtent: Double
    /// Height of the middle pane in a 3-row horizontal layout.
    @SceneStorage private var horizontalSecondaryExtent: Double

    init(storageKey: String, @ViewBuilder content: @escaping () -> Content) {
        self.storageKey = storageKey
        self.content = content
        self._verticalPaneCount = SceneStorage(wrappedValue: 1, "splittablePane.\(storageKey).verticalCount")
        self._horizontalPaneCount = SceneStorage(wrappedValue: 1, "splittablePane.\(storageKey).horizontalCount")
        self._verticalPrimaryExtent = SceneStorage(wrappedValue: 400, "splittablePane.\(storageKey).verticalPrimaryExtent")
        self._verticalSecondaryExtent = SceneStorage(wrappedValue: 400, "splittablePane.\(storageKey).verticalSecondaryExtent")
        self._horizontalPrimaryExtent = SceneStorage(wrappedValue: 320, "splittablePane.\(storageKey).horizontalPrimaryExtent")
        self._horizontalSecondaryExtent = SceneStorage(wrappedValue: 320, "splittablePane.\(storageKey).horizontalSecondaryExtent")
    }

    var body: some View {
        splitContainer
    }

    private var splitState: SplitPaneState {
        SplitPaneState(
            verticalPaneCount: verticalPaneCount,
            horizontalPaneCount: horizontalPaneCount
        )
    }

    private func updateSplitState(_ mutate: (inout SplitPaneState) -> Void) {
        var state = splitState
        mutate(&state)
        verticalPaneCount = state.verticalPaneCount
        horizontalPaneCount = state.horizontalPaneCount
    }

    private func toggleVertical() {
        updateSplitState { $0.toggleVertical() }
    }

    private func toggleHorizontal() {
        updateSplitState { $0.toggleHorizontal() }
    }

    private func collapseSplit() {
        updateSplitState { $0.collapseOnePane() }
    }

    private var splitAxisActions: SplitAxisActions {
        SplitAxisActions(
            hasVertical: splitState.hasVertical,
            hasHorizontal: splitState.hasHorizontal,
            paneCount: splitState.paneCount,
            onToggleVertical: toggleVertical,
            onToggleHorizontal: toggleHorizontal,
            onCollapseSplit: collapseSplit
        )
    }

    // MARK: Split container

    @ViewBuilder
    private var splitContainer: some View {
        if splitState.hasVertical {
            verticalSplitContainer
        } else if splitState.hasHorizontal {
            horizontalSplitContainer
        } else {
            splitPane(isSecondary: false)
        }
    }

    // MARK: Vertical split

    @ViewBuilder
    private var verticalSplitContainer: some View {
        GeometryReader { proxy in
            let available = proxy.size.width > 0
                ? Double(proxy.size.width)
                : verticalPrimaryExtent + 248
            let paneCount = splitState.verticalPaneCount
            let dividerWidth = 8.0
            let minimumWidth = 240.0
            let dividerSpace = Double(max(0, paneCount - 1)) * dividerWidth

            if paneCount == 2 {
                let maxPrimary = max(minimumWidth, available - dividerSpace - minimumWidth)
                let primaryWidth = CGFloat(clamp(verticalPrimaryExtent, lower: minimumWidth, upper: maxPrimary))

                HStack(spacing: 0) {
                    splitPane(isSecondary: false)
                        .frame(width: primaryWidth)

                    ResizableDivider(
                        width: $verticalPrimaryExtent,
                        minWidth: minimumWidth,
                        maxWidth: maxPrimary,
                        edge: .leading
                    )

                    splitPane(isSecondary: true)
                        .frame(minWidth: minimumWidth, maxWidth: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                let maxPrimary = max(minimumWidth, available - dividerSpace - (minimumWidth * 2))
                let primaryWidth = CGFloat(clamp(verticalPrimaryExtent, lower: minimumWidth, upper: maxPrimary))
                let remainingAfterPrimary = available - dividerSpace - Double(primaryWidth)
                let maxSecondary = max(minimumWidth, remainingAfterPrimary - minimumWidth)
                let secondaryWidth = CGFloat(clamp(verticalSecondaryExtent, lower: minimumWidth, upper: maxSecondary))

                HStack(spacing: 0) {
                    splitPane(isSecondary: false)
                        .frame(width: primaryWidth)

                    ResizableDivider(
                        width: $verticalPrimaryExtent,
                        minWidth: minimumWidth,
                        maxWidth: maxPrimary,
                        edge: .leading
                    )

                    splitPane(isSecondary: true)
                        .frame(width: secondaryWidth)

                    ResizableDivider(
                        width: $verticalSecondaryExtent,
                        minWidth: minimumWidth,
                        maxWidth: maxSecondary,
                        edge: .leading
                    )

                    splitPane(isSecondary: true)
                        .frame(minWidth: minimumWidth, maxWidth: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Horizontal split

    @ViewBuilder
    private var horizontalSplitContainer: some View {
        GeometryReader { proxy in
            let available = proxy.size.height > 0
                ? Double(proxy.size.height)
                : horizontalPrimaryExtent + 248
            let paneCount = splitState.horizontalPaneCount
            let dividerHeight = 8.0
            let minimumHeight = 160.0
            let dividerSpace = Double(max(0, paneCount - 1)) * dividerHeight

            if paneCount == 2 {
                let maxPrimary = max(minimumHeight, available - dividerSpace - minimumHeight)
                let primaryHeight = CGFloat(clamp(horizontalPrimaryExtent, lower: minimumHeight, upper: maxPrimary))

                VStack(spacing: 0) {
                    splitPane(isSecondary: false)
                        .frame(maxWidth: .infinity).frame(height: primaryHeight)

                    ResizableDivider(
                        width: $horizontalPrimaryExtent,
                        minWidth: minimumHeight,
                        maxWidth: maxPrimary,
                        edge: .leading,
                        axis: .vertical
                    )

                    splitPane(isSecondary: true)
                        .frame(maxWidth: .infinity, minHeight: minimumHeight, maxHeight: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                let maxPrimary = max(minimumHeight, available - dividerSpace - (minimumHeight * 2))
                let primaryHeight = CGFloat(clamp(horizontalPrimaryExtent, lower: minimumHeight, upper: maxPrimary))
                let remainingAfterPrimary = available - dividerSpace - Double(primaryHeight)
                let maxSecondary = max(minimumHeight, remainingAfterPrimary - minimumHeight)
                let secondaryHeight = CGFloat(clamp(horizontalSecondaryExtent, lower: minimumHeight, upper: maxSecondary))

                VStack(spacing: 0) {
                    splitPane(isSecondary: false)
                        .frame(maxWidth: .infinity).frame(height: primaryHeight)

                    ResizableDivider(
                        width: $horizontalPrimaryExtent,
                        minWidth: minimumHeight,
                        maxWidth: maxPrimary,
                        edge: .leading,
                        axis: .vertical
                    )

                    splitPane(isSecondary: true)
                        .frame(maxWidth: .infinity).frame(height: secondaryHeight)

                    ResizableDivider(
                        width: $horizontalSecondaryExtent,
                        minWidth: minimumHeight,
                        maxWidth: maxSecondary,
                        edge: .leading,
                        axis: .vertical
                    )

                    splitPane(isSecondary: true)
                        .frame(maxWidth: .infinity, minHeight: minimumHeight, maxHeight: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Pane helpers

    /// A secondary copy of `content()` with `isSecondarySplitPane = true`
    /// so that views suppress duplicate NSToolbar registrations.
    @ViewBuilder
    private func splitPane(isSecondary: Bool) -> some View {
        content()
            .environment(\.isSecondarySplitPane, isSecondary)
            .environment(\.splitAxisActions, splitAxisActions)
    }

    private func clamp(_ value: Double, lower: Double, upper: Double) -> Double {
        min(max(value, lower), upper)
    }
}
