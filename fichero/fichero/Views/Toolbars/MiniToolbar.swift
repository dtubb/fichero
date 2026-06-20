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

    // Split controls are injected by SplittablePane via environment so they
    // live inside the existing toolbar bar rather than requiring a separate
    // bar on top (#2309).
    @Environment(\.splitAxisActions) private var splitActions

    init(@ViewBuilder content: () -> Content, @ViewBuilder trailing: () -> Trailing) {
        self.content = content()
        self.trailing = trailing()
    }

    var body: some View {
        GlassEffectContainer {
            HStack(spacing: 12) {
                content
                if let actions = splitActions {
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
            .help(actions.hasVertical ? "Remove left/right split" : "Split left / right")

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
            .help(actions.hasHorizontal ? "Remove top/bottom split" : "Split top / bottom")
        }
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
            GlassEffectContainer {
                HStack(spacing: 6) {
                    content
                }
                .padding(.horizontal, 8)
                .frame(height: Self.height)
                .frame(maxWidth: .infinity)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
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

// MARK: - Common Mini Toolbar Patterns

/// A mini toolbar with a single action button on the right
struct ActionMiniToolbar: View {
    let title: String?
    let actionTitle: String
    let actionIcon: String?
    let action: () -> Void

    init(
        title: String? = nil,
        actionTitle: String,
        actionIcon: String? = nil,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.actionTitle = actionTitle
        self.actionIcon = actionIcon
        self.action = action
    }

    var body: some View {
        MiniToolbar {
            if let title = title {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button(action: action) {
                if let icon = actionIcon {
                    Label(actionTitle, systemImage: icon)
                } else {
                    Text(actionTitle)
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }
}

/// A mini toolbar with status text and optional actions
struct StatusMiniToolbar: View {
    let statusText: String
    let isLoading: Bool
    let actions: [ToolbarAction]

    struct ToolbarAction: Identifiable {
        let id = UUID()
        let title: String
        let icon: String?
        let action: () -> Void

        init(title: String, icon: String? = nil, action: @escaping () -> Void) {
            self.title = title
            self.icon = icon
            self.action = action
        }
    }

    init(
        statusText: String,
        isLoading: Bool = false,
        actions: [ToolbarAction] = []
    ) {
        self.statusText = statusText
        self.isLoading = isLoading
        self.actions = actions
    }

    var body: some View {
        MiniToolbar {
            if isLoading {
                ProgressView()
                    .scaleEffect(0.7)
                    .padding(.trailing, 4)
            }

            Text(statusText)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            ForEach(actions) { action in
                Button(
                    action: action.action,
                    label: {
                        if let icon = action.icon {
                            Label(action.title, systemImage: icon)
                        } else {
                            Text(action.title)
                        }
                    }
                )
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }
}

/// A mini toolbar with a segmented picker
struct PickerMiniToolbar<T: Hashable>: View {
    struct PickerOption: Identifiable {
        let id = UUID()
        let value: T
        let label: String
        let icon: String?

        init(value: T, label: String, icon: String? = nil) {
            self.value = value
            self.label = label
            self.icon = icon
        }
    }

    struct ToolbarAction: Identifiable {
        let id = UUID()
        let title: String
        let icon: String
        let action: () -> Void
    }

    let title: String?
    @Binding var selection: T
    let options: [PickerOption]
    let actions: [ToolbarAction]

    init(
        title: String? = nil,
        selection: Binding<T>,
        options: [PickerOption],
        actions: [ToolbarAction] = []
    ) {
        self.title = title
        self._selection = selection
        self.options = options
        self.actions = actions
    }

    var body: some View {
        MiniToolbar {
            if let title = title {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Picker("", selection: $selection) {
                ForEach(options) { option in
                    if let icon = option.icon {
                        Label(option.label, systemImage: icon)
                            .tag(option.value)
                    } else {
                        Text(option.label)
                            .tag(option.value)
                    }
                }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 300)

            if !actions.isEmpty {
                Spacer()

                ForEach(actions) { action in
                    Button(action: action.action) {
                        Image(systemName: action.icon)
                    }
                    .help(action.title)
                }
            }
        }
    }
}

// MARK: - Workflow Button (#2415)

/// Reusable "Run Workflow" bolt button for inclusion in `MiniToolbar` content or
/// `PickerMiniToolbar` actions. Hidden when `isWorkflowRunOnSelectionEnabled` is off.
/// The caller is responsible for presenting `WorkflowPickerSheet` on `action`.
struct WorkflowMiniToolbarButton: View {
    let isEnabled: Bool
    let action: () -> Void

    @ObservedObject private var featureManager = FeatureManager.shared

    var body: some View {
        if featureManager.isWorkflowRunOnSelectionEnabled {
            Button(action: action) {
                Image(systemName: "bolt")
                    .accessibilityLabel("Run Workflow")
            }
            .buttonStyle(.plain)
            .foregroundStyle(isEnabled ? Color.accentColor : Color.secondary)
            .disabled(!isEnabled)
            .help("Run Workflow on Selection")
        }
    }
}

// MARK: - Preview

#Preview("Basic MiniToolbar") {
    VStack(spacing: 0) {
        MiniToolbar {
            Button("Action 1") { }
            Spacer()
            Button("Action 2") { }
            Button("Action 3") { }
        }

        Text("Content below")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }
    .frame(width: 600, height: 200)
}

#Preview("ActionMiniToolbar") {
    VStack(spacing: 0) {
        ActionMiniToolbar(
            title: "Inspector",
            actionTitle: "Add Field",
            actionIcon: "plus"
        ) {
            print("Add tapped")
        }

        Text("Inspector content")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }
    .frame(width: 300, height: 400)
}

#Preview("StatusMiniToolbar") {
    VStack(spacing: 0) {
        StatusMiniToolbar(
            statusText: "3 items",
            actions: [
                .init(title: "Filter", icon: "line.3.horizontal.decrease.circle", action: {}),
                .init(title: "Sort", icon: "arrow.up.arrow.down", action: {})
            ]
        )

        Text("List content")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
    }
    .frame(width: 400, height: 300)
}

#Preview("PickerMiniToolbar") {
    struct PreviewWrapper: View {
        @State private var viewMode: String = "grid"

        var body: some View {
            VStack(spacing: 0) {
                PickerMiniToolbar(
                    title: "View",
                    selection: $viewMode,
                    options: [
                        .init(value: "grid", label: "Grid", icon: "square.grid.2x2"),
                        .init(value: "list", label: "List", icon: "list.bullet"),
                        .init(value: "detail", label: "Detail", icon: "list.bullet.below.rectangle")
                    ],
                    actions: [
                        .init(title: "Settings", icon: "gear", action: {})
                    ]
                )

                Text("Content in \(viewMode) mode")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color(.textBackgroundColor))
            }
            .frame(width: 500, height: 300)
        }
    }

    return PreviewWrapper()
}

#Preview("Using View Extension") {
    ScrollView {
        ForEach(0..<20) { index in
            Text("Item \(index)")
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color(.controlBackgroundColor))
        }
    }
    .miniToolbar {
        Text("20 items")
            .font(.caption)
            .foregroundStyle(.secondary)
        Spacer()
        Button("Add") { }
            .buttonStyle(.bordered)
            .controlSize(.small)
    }
    .frame(width: 400, height: 500)
}
