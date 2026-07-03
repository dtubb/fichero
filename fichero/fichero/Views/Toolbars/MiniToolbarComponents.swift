import SwiftUI

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

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

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

            styledPicker

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

    private var picker: some View {
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
    }

    /// Segmented on Mac/iPad-regular (capped width); menu on a compact iPhone
    /// toolbar, where several segments overflow (#2806).
    @ViewBuilder
    private var styledPicker: some View {
        #if os(macOS)
        picker
            .pickerStyle(.segmented)
            .frame(maxWidth: 300)
        #else
        if horizontalSizeClass == .compact {
            picker
                .pickerStyle(.menu)
        } else {
            picker
                .pickerStyle(.segmented)
                .frame(maxWidth: 300)
        }
        #endif
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
