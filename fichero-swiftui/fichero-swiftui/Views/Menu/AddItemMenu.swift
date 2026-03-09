import SwiftUI

/// Reusable "+ Add Item" menu component
/// Uses focused sidebar actions so toolbar and Data menu stay aligned.
struct AddItemMenu: View {
    @ObservedObject var registry: ItemTypeRegistry
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
        if let sidebarActions {
            Button("New Folder") {
                sidebarActions.createFolder()
            }

            Menu("Import") {
                Button("Link Files...") {
                    sidebarActions.importFiles(.link)
                }

                Button("Copy Files...") {
                    sidebarActions.importFiles(.copy)
                }

                Button("Add Files...") {
                    sidebarActions.importFiles(.move)
                }
            }

            Divider()

            Button("New Search") {
                sidebarActions.createSearch()
            }

            if featureManager.isChatEnabled {
                Button("New Chat") {
                    sidebarActions.createChat()
                }
            }

            if featureManager.isWorkflowsEnabled {
                Button("New Workflow") {
                    sidebarActions.createWorkflow()
                }
            }

            if featureManager.isAutomationEnabled {
                Button("New Schedule") {
                    sidebarActions.createSchedule()
                }
            }
        }
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
