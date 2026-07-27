import SwiftUI

/// Reusable "+ Add Item" menu component
/// Uses focused sidebar actions so toolbar and Data menu stay aligned.
struct AddItemMenu: View {
    @Bindable var registry: ItemTypeRegistry
    let style: MenuStyle

    // Feature manager to filter menu items
    let featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarActions) private var sidebarActions

    enum MenuStyle {
        case button      // Toolbar button with menu
        case contextual  // Context menu
        case inline      // Inline menu content
    }

    var body: some View {
        switch style {
        case .button:
            Menu {
                menuContent
            } label: {
                Label("Add", systemImage: "plus")
            }
            .menuStyle(.borderlessButton)

        case .contextual:
            menuContent

        case .inline:
            menuContent
        }
    }

    @ViewBuilder
    private var menuContent: some View {
        if let createFolderAction {
            Button("New Folder") {
                createFolderAction()
            }

            Menu("Import") {
                Button("Link Files...") {
                    importLinkAction?()
                }
                .disabled(importLinkAction == nil)

                Button("Copy Files...") {
                    importCopyAction?()
                }
                .disabled(importCopyAction == nil)

                Button("Move Files...") {
                    importMoveAction?()
                }
                .disabled(importMoveAction == nil)
            }
            .disabled(importLinkAction == nil && importCopyAction == nil && importMoveAction == nil)

            Divider()

            if featureManager.isChatEnabled {
                Button(featureManager.badgedLabel("New Chat", for: .chat)) {
                    createChatAction?()
                }
                .disabled(createChatAction == nil)
            }

            if featureManager.isWorkflowsEnabled {
                Button(featureManager.badgedLabel("New Workflow", for: .workflows)) {
                    createWorkflowAction?()
                }
                .disabled(createWorkflowAction == nil)
                // One gate for Comparison everywhere (#4121): it rode
                // isWorkflowsEnabled in the toolbar and a stricter flag in
                // the Data menu — the shared menu settles on workflows.
                Button(featureManager.badgedLabel("New Comparison", for: .modelComparison)) {
                    createComparisonAction?()
                }
                .disabled(createComparisonAction == nil)
                if featureManager.isWorkflowChainsEnabled {
                    Button(featureManager.badgedLabel("New Chain", for: .workflowChains)) {
                        createChainAction?()
                    }
                    .disabled(createChainAction == nil)
                }
            }

            if featureManager.isAutomationEnabled {
                Button(featureManager.badgedLabel("New Schedule", for: .automation)) {
                    createScheduleAction?()
                }
                .disabled(createScheduleAction == nil)
                Button(featureManager.badgedLabel("New Trigger", for: .automation)) {
                    createTriggerAction?()
                }
                .disabled(createTriggerAction == nil)
            }
        } else {
            Text("No create actions available")
        }
    }

    private var createFolderAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createFolder
        }
        return registry.createFolder
    }

    private var importLinkAction: (() -> Void)? {
        if let sidebarActions {
            return { sidebarActions.importFiles(.link) }
        }
        return registry.importFiles
    }

    private var importCopyAction: (() -> Void)? {
        if let sidebarActions {
            return { sidebarActions.importFiles(.copy) }
        }
        return registry.importFiles
    }

    private var importMoveAction: (() -> Void)? {
        if let sidebarActions {
            return { sidebarActions.importFiles(.move) }
        }
        return registry.importFiles
    }

    private var createComparisonAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createComparison
        }
        return registry.createComparison
    }

    private var createChainAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createChain
        }
        return registry.createChain
    }

    private var createTriggerAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createTrigger
        }
        return registry.createTrigger
    }

    private var createChatAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createChat
        }
        return registry.createChat
    }

    private var createWorkflowAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createWorkflow
        }
        return registry.createWorkflow
    }

    private var createScheduleAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createSchedule
        }
        return registry.createSchedule
    }
}

#Preview {
    let registry = ItemTypeRegistry()
    registry.createFolder = { print("Create folder") }
    registry.createChat = { print("Create chat") }
    registry.createWorkflow = { print("Create workflow") }

    return AddItemMenu(registry: registry, style: .button)
}
