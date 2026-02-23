import SwiftUI

/// Reusable "+ Add Item" menu component
/// Uses ItemTypeRegistry to generate menu items grouped by category
struct AddItemMenu: View {
    @ObservedObject var registry: ItemTypeRegistry
    let style: MenuStyle

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
        let grouped = registry.definitionsByCategory

        // Documents category
        if let items = grouped[.documents], !items.isEmpty {
            Section("Documents") {
                ForEach(items) { item in
                    buttonWithShortcut(for: item)
                }
            }
        }

        // AI category
        if let items = grouped[.aiTools], !items.isEmpty {
            Section("AI") {
                ForEach(items) { item in
                    buttonWithShortcut(for: item)
                }
            }
        }

        // Automation category
        if let items = grouped[.automation], !items.isEmpty {
            Section("Automation") {
                ForEach(items) { item in
                    buttonWithShortcut(for: item)
                }
            }
        }

        // Places category
        if let items = grouped[.places], !items.isEmpty {
            Section("Places") {
                ForEach(items) { item in
                    buttonWithShortcut(for: item)
                }
            }
        }

        // Tools category
        if let items = grouped[.tools], !items.isEmpty {
            Section("Tools") {
                ForEach(items) { item in
                    buttonWithShortcut(for: item)
                }
            }
        }
    }

    /// Create button with optional keyboard shortcut
    @ViewBuilder
    private func buttonWithShortcut(for item: ItemTypeDefinition) -> some View {
        if let keyEquiv = keyEquivalent(for: item.keyboardShortcut) {
            Button(action: item.handler) {
                Label(item.name, systemImage: item.icon)
            }
            .keyboardShortcut(keyEquiv, modifiers: [.command])
        } else {
            Button(action: item.handler) {
                Label(item.name, systemImage: item.icon)
            }
        }
    }

    /// Convert string keyboard shortcut to KeyEquivalent
    private func keyEquivalent(for shortcut: String?) -> KeyEquivalent? {
        guard let shortcut = shortcut,
              !shortcut.isEmpty,
              let char = shortcut.first else {
            return nil
        }
        return KeyEquivalent(char)
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
