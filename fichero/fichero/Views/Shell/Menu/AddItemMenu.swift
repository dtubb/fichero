import SwiftUI

/// Reusable "+ Add Item" menu component
/// Uses focused sidebar actions so toolbar and Data menu stay aligned.
struct AddItemMenu: View {
    @Bindable var registry: ItemTypeRegistry
    let style: MenuStyle

    // Feature manager to filter menu items
    @ObservedObject var featureManager = FeatureManager.shared
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

            if featureManager.isSearchEnabled {
                Button("New Search") {
                    createSearchAction?()
                }
                .disabled(createSearchAction == nil)
            }

            if featureManager.isChatEnabled {
                Button(featureManager.badgedLabel("New Chat", for: .chat)) {
                    createChatAction?()
                }
                .disabled(createChatAction == nil)
            }

            if featureManager.isWorkflowsEnabled {
                Button("New Workflow") {
                    createWorkflowAction?()
                }
                .disabled(createWorkflowAction == nil)
            }

            if featureManager.isAutomationEnabled {
                Button(featureManager.badgedLabel("New Schedule", for: .automation)) {
                    createScheduleAction?()
                }
                .disabled(createScheduleAction == nil)
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

    private var createSearchAction: (() -> Void)? {
        if let sidebarActions {
            return sidebarActions.createSearch
        }
        return registry.createSearch
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
    registry.createSearch = { print("Create search") }
    registry.createChat = { print("Create chat") }
    registry.createWorkflow = { print("Create workflow") }

    return AddItemMenu(registry: registry, style: .button)
}
