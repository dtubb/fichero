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

/// Button that calls whichever focused pane implements import — the
/// sidebar's `sidebarActions.importFiles`, or (#4452) the library content
/// pane's narrower `libraryImportAction` when IT has focus instead. Never
/// falls back to a stub: if neither pane publishes one, `importAction` is
/// nil and the menu stays disabled, per #4449/#4452's silent-no-op rule.
struct FocusedImportFilesButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.libraryImportAction) private var libraryImportAction

    private var importAction: ((IngestMode) -> Void)? {
        sidebarActions?.importFiles ?? libraryImportAction
    }

    var body: some View {
        Menu("Import") {
            Button("Link Files...") {
                importAction?(.link)
            }
            .keyboardShortcut("i", modifiers: [.command])

            Button("Copy Files...") {
                importAction?(.copy)
            }
            .keyboardShortcut("i", modifiers: [.command, .option])

            Button("Move Files...") {
                importAction?(.move)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
        }
        .disabled(importAction == nil)
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

/// Button that calls the focused sidebar's deleteItem action — the same
/// batch path as the Delete key, so the title counts the deletable
/// selection and the enabled state matches what the key would remove.
struct FocusedDeleteButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    private var deletableCount: Int {
        selectionInfo?.deletableCount ?? 0
    }

    var body: some View {
        Button(deletableCount > 1 ? "Delete \(deletableCount) Items" : "Delete") {
            sidebarActions?.deleteItem()
        }
        .disabled(deletableCount == 0)
    }
}
