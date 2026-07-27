import SwiftUI

// Pure shell layout/routing policy, extracted from ContentView+State.swift to
// keep that file under the 1000-line hard limit (#3035). No behavior change —
// these are the same `extension ContentView` statics + the compact routing
// enums, so every call site (ContentView.shouldUseSplittablePane,
// CompactShellPolicy.route, …) is unchanged. Kept as static/pure so the shell
// policy stays unit-testable without a live ContentView.

extension ContentView {

    struct ShellCollapsePolicy: Equatable {
        let collapseSidebar: Bool
        let collapseInspector: Bool
    }

    // nonisolated: pure — reads only its argument + a compile-time `#if`, touches no
    // main-actor state. Lets nonisolated policy callers (AdaptiveAppleShellRoute.resolve,
    // CompactShellPolicy.route) invoke it without crossing the actor boundary (#3977).
    nonisolated static func shouldUseCompactNavigationFlow(horizontalSizeClass: UserInterfaceSizeClass?) -> Bool {
        #if os(macOS)
        false
        #else
        horizontalSizeClass == .compact
        #endif
    }

    static func shouldUseSplittablePane(
        horizontalSizeClass: UserInterfaceSizeClass?,
        windowWidth: Double? = nil,
        minimumWidth: Double? = nil
    ) -> Bool {
        #if os(macOS)
        if horizontalSizeClass == .compact {
            return false
        }
        #else
        if horizontalSizeClass == .compact {
            return false
        }
        #endif

        guard let windowWidth, let minimumWidth else {
            return true
        }

        return windowWidth >= minimumWidth
    }

    static func shouldRenderSidebarColumn(
        horizontalSizeClass: UserInterfaceSizeClass?,
        showSidebar: Bool,
        columnVisibility: NavigationSplitViewVisibility
    ) -> Bool {
        showSidebar && horizontalSizeClass != .compact && columnVisibility != .detailOnly
    }

    static func shellCollapsePolicy(
        windowWidth: Double?,
        horizontalSizeClass: UserInterfaceSizeClass?,
        sidebarVisible: Bool,
        inspectorVisible: Bool,
        detailMinWidth: Double
    ) -> ShellCollapsePolicy {
        #if os(macOS)
        if horizontalSizeClass == .compact {
            return ShellCollapsePolicy(collapseSidebar: true, collapseInspector: false)
        }
        #else
        if horizontalSizeClass == .compact {
            return ShellCollapsePolicy(collapseSidebar: true, collapseInspector: false)
        }
        #endif

        guard let windowWidth, windowWidth > 0 else {
            return ShellCollapsePolicy(collapseSidebar: false, collapseInspector: false)
        }

        let sidebarMinWidth = sidebarVisible ? ContentView.sidebarMinWidth : 0
        let inspectorMinWidth = inspectorVisible ? ContentView.inspectorMinWidth : 0
        let collapseInspector =
            inspectorVisible &&
            windowWidth < detailMinWidth + sidebarMinWidth + inspectorMinWidth
        let collapseSidebar =
            sidebarVisible &&
            windowWidth < detailMinWidth + sidebarMinWidth

        return ShellCollapsePolicy(
            collapseSidebar: collapseSidebar,
            collapseInspector: collapseInspector
        )
    }

    static func shellWindowMinWidth(
        windowWidth: Double?,
        horizontalSizeClass: UserInterfaceSizeClass?,
        sidebarVisible: Bool,
        inspectorVisible: Bool,
        detailMinWidth: Double
    ) -> Double {
        // On a compact (iPhone-width) layout the single content column must be
        // free to shrink to the screen. `paneAwareDetailMinWidth` can return a
        // 520pt content minimum (entity-library / KG / chat, where the reading
        // workspace is off), which on a 390–430pt phone clamps content
        // off-screen (#2801). A runtime check, not `#if os(iOS)`: macOS never
        // reports a compact horizontal size class, so its shell minimum below is
        // unchanged, and this stays unit-testable on the macOS test target.
        if horizontalSizeClass == .compact {
            return 0
        }

        let policy = shellCollapsePolicy(
            windowWidth: windowWidth,
            horizontalSizeClass: horizontalSizeClass,
            sidebarVisible: sidebarVisible,
            inspectorVisible: inspectorVisible,
            detailMinWidth: detailMinWidth
        )
        let effectiveInspectorVisible = inspectorVisible && !policy.collapseInspector

        if policy.collapseSidebar {
            return detailMinWidth
        }

        return windowMinWidth(
            sidebarVisible: sidebarVisible,
            inspectorVisible: effectiveInspectorVisible,
            detailMinWidth: detailMinWidth
        )
    }
}

// MARK: - Compact center-content routing (#3009)

/// The compact-width `centerContent` route for the active mode. Kept separate
/// from the regular-width split path so the compact policy has one home.
enum CompactShellRoute: Equatable {
    /// Regular width (Mac / iPad-regular): the split preview layout — unchanged.
    case regular
    /// Compact library/search: the list is the `NavigationStack` root and
    /// tapping a leaf pushes the reader (#2551).
    case libraryReader
    /// Compact non-library mode (chat, workflows, activity, …): the mode owns
    /// the full content area itself, no preview split.
    case modeContent
}

/// Pure routing policy for the compact (iPhone-width) center content. Replaces
/// the ad-hoc `usesCompactReaderFlow` switch with an **exhaustive** per-mode map
/// — no `default` fallthrough, so adding an `AppViewMode` fails to compile until
/// its compact route is decided (#3009).
enum CompactShellPolicy {
    static func route(
        horizontalSizeClass: UserInterfaceSizeClass?,
        appViewMode: AppViewMode,
        isEntitySelection: Bool
    ) -> CompactShellRoute {
        guard ContentView.shouldUseCompactNavigationFlow(
            horizontalSizeClass: horizontalSizeClass
        ) else {
            return .regular
        }
        switch appViewMode {
        case .library:
            // The entities browser is a non-reader library selection — it owns
            // its own content (the KG browser), so it takes the mode path.
            return isEntitySelection ? .modeContent : .libraryReader
        case .chat, .comparison, .workflow, .chain, .batches, .batch,
             .automation, .schedule, .trigger, .activity:
            return .modeContent
        }
    }
}
