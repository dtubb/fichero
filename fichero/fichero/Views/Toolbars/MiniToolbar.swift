import SwiftUI

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
struct MiniToolbar<Content: View>: View {
    /// Fixed height for all pane mini-toolbars so the list-view mode strip,
    /// preview pane toolbar, and inspector tab strip line up across the
    /// window. Daniel: 'the height of the toolbar for the list view, the
    /// preview pane, and the inspector' should match.
    static var standardHeight: CGFloat { 36 }

    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        HStack(spacing: 12) {
            content
        }
        .padding(.horizontal, 12)
        .frame(height: Self.standardHeight)
    }
}

/// View extension for easily adding mini toolbars to any view
extension View {
    /// Adds a mini toolbar above this view using the standard material and spacing.
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
        VStack(spacing: 0) {
            MiniToolbar(content: content)
            self
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
