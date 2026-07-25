import SwiftUI

// MARK: - Focused Command Buttons

/// Button that calls the focused sidebar's createFolder action
struct FocusedNewFolderButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Folder") {
            sidebarActions?.createFolder()
        }
        .keyboardShortcut("n", modifiers: [.command, .shift])
        .disabled(sidebarActions == nil)
    }
}

/// Button that calls the focused sidebar's importFiles action
struct FocusedImportFilesButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Menu("Import") {
            Button("Link Files...") {
                sidebarActions?.importFiles(.link)
            }
            .keyboardShortcut("i", modifiers: [.command])

            Button("Copy Files...") {
                sidebarActions?.importFiles(.copy)
            }
            .keyboardShortcut("i", modifiers: [.command, .option])

            Button("Move Files...") {
                sidebarActions?.importFiles(.move)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that calls the focused sidebar's renameItem action.
///
/// Keyboard shortcut: plain Return (no modifier) — matches Finder's
/// sidebar convention where pressing Return on a selected row starts
/// rename. Scoped via `@FocusedValue` so the shortcut is only active
/// when the sidebar has focus.
struct FocusedRenameButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Rename") {
            sidebarActions?.renameItem()
        }
        .keyboardShortcut(.return, modifiers: [])
        .disabled(!(selectionInfo?.canRename ?? false))
    }
}

/// File-menu "Open in New Tab" for the focused sidebar's selected row —
/// keyboard-discoverable parity with double-click and the row context menu
/// (#2496). ⌘O is Open Library, so selection-opens take the ⌘⌥O family.
struct FocusedOpenInNewTabButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Open in New Tab") {
            sidebarActions?.openSelectionInNewTab()
        }
        .keyboardShortcut("o", modifiers: [.command, .option])
        .disabled(selectionInfo?.selectedItem == nil)
    }
}

/// File-menu "Open in New Window" sibling of `FocusedOpenInNewTabButton`.
struct FocusedOpenInNewWindowButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Open in New Window") {
            sidebarActions?.openSelectionInNewWindow()
        }
        .keyboardShortcut("o", modifiers: [.command, .option, .shift])
        .disabled(selectionInfo?.selectedItem == nil)
    }
}

/// Button that calls the focused sidebar's deleteItem action
struct FocusedDeleteButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Delete") {
            sidebarActions?.deleteItem()
        }
        .disabled(!(selectionInfo?.canDelete ?? false))
    }
}
