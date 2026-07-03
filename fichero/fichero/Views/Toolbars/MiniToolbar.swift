import SwiftUI

struct MiniToolbarMetrics: Equatable {
    let standardHeight: CGFloat
    let touchTargetSide: CGFloat
}

enum MiniToolbarMetricPolicy {
    static func metrics(isMac: Bool, isTV: Bool) -> MiniToolbarMetrics {
        if isMac {
            return MiniToolbarMetrics(standardHeight: 44, touchTargetSide: 28)
        }
        if isTV {
            return MiniToolbarMetrics(standardHeight: 64, touchTargetSide: 44)
        }
        return MiniToolbarMetrics(standardHeight: 52, touchTargetSide: 44)
    }
}

/// App-wide show/hide preference for reader mini-toolbars (#2460).
/// Non-generic companion so the constants are accessible without specifying
/// MiniToolbar's generic type parameters. Key must stay in sync with
/// ShowMiniToolbarToggle and MiniToolbarGate.
enum MiniToolbarPreferences {
    static let toolbarVisibilityKey: String = "fichero.ui.showMiniToolbar"
    static let toolbarVisibilityDefault: Bool = true
}

/// A standardized mini toolbar component that can be used consistently across the app.
/// Provides a translucent bar with automatic spacing, padding, and material background.
///
/// Usage:
/// ```swift
/// VStack(spacing: 0) {
///     MiniToolbar {
///         Button("Action") { }
///         Spacer()
///         Text("Info")
///     }
///     // Your content below
/// }
/// ```
struct MiniToolbar<Content: View, Trailing: View>: View {
    /// Fixed height for all pane mini-toolbars so the list-view mode strip,
    /// preview pane toolbar, and inspector tab strip line up across the
    /// window. Daniel: 'the height of the toolbar for the list view, the
    /// preview pane, and the inspector' should match. 44pt matches
    /// NSToolbar's default regular-size height so pane headers visually
    /// rhyme with the window toolbar above them. (#883)
    static var standardHeight: CGFloat {
        platformMetrics.standardHeight
    }

    static var touchTargetSide: CGFloat {
        platformMetrics.touchTargetSide
    }

    private static var platformMetrics: MiniToolbarMetrics {
        #if os(macOS)
        MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false)
        #elseif os(tvOS)
        MiniToolbarMetricPolicy.metrics(isMac: false, isTV: true)
        #else
        MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false)
        #endif
    }

    let content: Content
    /// Items appended to the far right, after split-axis buttons.
    /// Use for the pin button or other trailing actions.
    let trailing: Trailing

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    // Split controls are injected by SplittablePane via environment so they
    // live inside the existing toolbar bar rather than requiring a separate
    // bar on top (#2309).
    @Environment(\.splitAxisActions) private var splitActions

    private var shouldShowSplitButtons: Bool {
        horizontalSizeClass != .compact
    }

    init(@ViewBuilder content: () -> Content, @ViewBuilder trailing: () -> Trailing) {
        self.content = content()
        self.trailing = trailing()
    }

    var body: some View {
        #if os(visionOS)
        HStack(spacing: 12) {
            content
            if let actions = splitActions, shouldShowSplitButtons {
                splitButtonsView(for: actions)
            }
            trailing
        }
        .padding(.horizontal, 12)
        .frame(height: Self.standardHeight)
        .controlSize(.regular)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        #else
        GlassEffectContainer {
            HStack(spacing: 12) {
                content
                if let actions = splitActions, shouldShowSplitButtons {
                    splitButtonsView(for: actions)
                }
                trailing
            }
            .padding(.horizontal, 12)
            .frame(height: Self.standardHeight)
            #if !os(macOS)
            .controlSize(.regular)
            #endif
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 10))
        }
        #endif
    }

    /// Split-axis glyph font. Uses a *semantic* style so the icon scales with
    /// the system text size (Dynamic Type) instead of a fixed point size, and
    /// is noticeably larger on touch platforms where the old hardcoded 11pt
    /// glyph was too small to read/hit comfortably (Daniel, iOS/iPad). Mac keeps
    /// the compact NSToolbar-style chrome. (#883)
    private var splitIconFont: Font {
        #if os(macOS)
        .body
        #elseif os(tvOS)
        .largeTitle
        #else
        .title2
        #endif
    }

    @ViewBuilder
    private func splitButtonsView(for actions: SplitAxisActions) -> some View {
        ViewThatFits(in: .horizontal) {
            splitButtonsRow(for: actions)
            splitButtonsMenu(for: actions)
        }
    }

    @ViewBuilder
    private func splitButtonsRow(for actions: SplitAxisActions) -> some View {
        let verticalHelp = actions.hasVertical
            ? (actions.paneCount == 3 ? "Remove vertical split" : "Add a third vertical pane")
            : "Split left / right"
        let horizontalHelp = actions.hasHorizontal
            ? (actions.paneCount == 3 ? "Remove horizontal split" : "Add a third horizontal pane")
            : "Split top / bottom"

        HStack(spacing: 4) {
            Divider().frame(height: 16)

            Button { actions.onToggleVertical() } label: {
                Image(systemName: "rectangle.split.2x1")
                    .font(splitIconFont)
                    .frame(
                        minWidth: Self.touchTargetSide,
                        minHeight: Self.touchTargetSide
                    )
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(actions.hasVertical ? Color.accentColor : Color.secondary)
            .help(verticalHelp)
            .accessibilityLabel(verticalHelp)

            Button { actions.onToggleHorizontal() } label: {
                Image(systemName: "rectangle.split.1x2")
                    .font(splitIconFont)
                    .frame(
                        minWidth: Self.touchTargetSide,
                        minHeight: Self.touchTargetSide
                    )
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(actions.hasHorizontal ? Color.accentColor : Color.secondary)
            .help(horizontalHelp)
            .accessibilityLabel(horizontalHelp)
        }
    }

    @ViewBuilder
    private func splitButtonsMenu(for actions: SplitAxisActions) -> some View {
        let verticalTitle = actions.hasVertical
            ? (actions.paneCount == 3 ? "Remove Vertical Split" : "Add Third Vertical Pane")
            : "Split Left / Right"
        let horizontalTitle = actions.hasHorizontal
            ? (actions.paneCount == 3 ? "Remove Horizontal Split" : "Add Third Horizontal Pane")
            : "Split Top / Bottom"

        Menu {
            Button {
                actions.onToggleVertical()
            } label: {
                Label(
                    verticalTitle,
                    systemImage: "rectangle.split.2x1"
                )
            }

            Button {
                actions.onToggleHorizontal()
            } label: {
                Label(
                    horizontalTitle,
                    systemImage: "rectangle.split.1x2"
                )
            }
        } label: {
            Label("Split", systemImage: "rectangle.split.2x1")
                .font(splitIconFont)
                .frame(
                    minWidth: Self.touchTargetSide,
                    minHeight: Self.touchTargetSide
                )
                .contentShape(Rectangle())
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
    }
}

// Backward-compat: callers using `MiniToolbar { ... }` (no trailing) work unchanged.
extension MiniToolbar where Trailing == EmptyView {
    init(@ViewBuilder content: () -> Content) {
        self.init(content: content, trailing: { EmptyView() })
    }
}

// MARK: - Conditional searchable (split-pane crash prevention)

extension View {
    /// Applies `.searchable()` only when `isActive` is true.
    /// Use this in any view that registers a toolbar search field so that
    /// secondary split-pane copies don't double-register the NSToolbar item,
    /// which would crash the toolbar subsystem (#2309).
    @ViewBuilder
    func conditionalSearchable(
        text: Binding<String>,
        placement: SearchFieldPlacement,
        prompt: LocalizedStringKey,
        isActive: Bool
    ) -> some View {
        if isActive {
            self.searchable(text: text, placement: placement, prompt: prompt)
        } else {
            self
        }
    }
}

// MARK: - Lozenge Toggle Button (Xcode filter-bar style)

/// A small pill-shaped toggle button matching Xcode's Navigator filter bar.
/// Active state shows an accent fill; inactive state is borderless and secondary.
///
/// Use inside bottom filter bars to let the user toggle visibility of document
/// categories, entity types, or status filters.
struct LozengeButton: View {
    let title: String
    let icon: String?
    let isActive: Bool
    let action: () -> Void

    init(_ title: String, icon: String? = nil, isActive: Bool, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.isActive = isActive
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 3) {
                if let icon {
                    Image(systemName: icon)
                        .font(.caption2.weight(.medium))
                }
                if !title.isEmpty {
                    Text(title)
                        .font(.caption.weight(.medium))
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(isActive ? Color.accentColor.opacity(0.15) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(
                        isActive ? Color.accentColor.opacity(0.35) : Color.primary.opacity(0.12),
                        lineWidth: 0.5
                    )
            )
        }
        .buttonStyle(.plain)
        .foregroundStyle(isActive ? Color.accentColor : Color.secondary)
        .help(title)
    }
}

// MARK: - Pane Filter Bar (bottom of content panes)

/// 24pt compact bar — matches Xcode's Navigator filter bar height.
/// Use at the bottom of sidebar / library / inspector panes in place of
/// a full `MiniToolbar` when only filter lozenges and small action buttons
/// are needed.
struct PaneFilterBar<Content: View>: View {
    static var height: CGFloat { 24 }

    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 0) {
            Divider()
            #if os(visionOS)
            HStack(spacing: 6) {
                content
            }
            .padding(.horizontal, 8)
            .frame(height: Self.height)
            .frame(maxWidth: .infinity)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            #else
            GlassEffectContainer {
                HStack(spacing: 6) {
                    content
                }
                .padding(.horizontal, 8)
                .frame(height: Self.height)
                .frame(maxWidth: .infinity)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
            #endif
        }
    }
}

/// View extension for easily adding mini toolbars to any view
extension View {
    /// Adds a mini toolbar above this view using the standard material and spacing.
    /// Respects the user's "Show Mini Toolbar" preference (#2460): when the
    /// preference is off the toolbar is omitted and the content fills the space.
    ///
    /// Example:
    /// ```swift
    /// ScrollView {
    ///     // content
    /// }
    /// .miniToolbar {
    ///     Button("Filter") { }
    ///     Spacer()
    ///     Button("Sort") { }
    /// }
    /// ```
    func miniToolbar<Content: View>(
        @ViewBuilder content: () -> Content
    ) -> some View {
        MiniToolbarGate(bottom: self, toolbar: MiniToolbar(content: content))
    }
}

/// Gates the `.miniToolbar {}` extension behind the app-wide show/hide preference.
/// Using a dedicated view struct (rather than an `if` inside the extension) gives
/// AppStorage the stable identity it needs to re-render when UserDefaults changes.
private struct MiniToolbarGate<Bottom: View, Toolbar: View>: View {
    // Keep key in sync with MiniToolbar.toolbarVisibilityKey (#2460).
    @AppStorage("fichero.ui.showMiniToolbar") private var isVisible = true
    let bottom: Bottom
    let toolbar: Toolbar

    var body: some View {
        VStack(spacing: 0) {
            if isVisible {
                toolbar
            }
            bottom
        }
    }
}
