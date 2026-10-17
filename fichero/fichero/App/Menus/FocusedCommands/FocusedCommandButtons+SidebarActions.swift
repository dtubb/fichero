import SwiftUI

// MARK: - Focused Command Buttons

/// File › New Folder (⇧⌘N) in the focused pane's place: the Items list's folder, else the sidebar's selection.
/// The context menus' own item (#5652).
struct FocusedNewFolderButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions

    private var create: (@MainActor () -> Void)? {
        if let newFolder = items?.newFolder { return newFolder }
        guard let actions = sidebarActions else { return nil }
        return { actions.createFolder() }
    }

    var body: some View {
        NewFolderMenuItem(create: create)
            .keyboardShortcut("n", modifiers: [.command, .shift])
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
        sidebarActions?.importFiles ?? libraryImportAction?.run
    }

    var body: some View {
        Menu("Import") {
            #if os(macOS)  // a phone imports by copy only: no link, no move (#3282)
            Button("Link Files...") {
                importAction?(.link)
            }
            .keyboardShortcut("i", modifiers: [.command])

            #endif
            Button("Copy Files...") {
                importAction?(.copy)
            }
            .keyboardShortcut("i", modifiers: [.command, .option])

            #if os(macOS)
            Button("Move Files...") {
                importAction?(.move)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
            #endif
        }
        .disabled(importAction == nil)
    }
}

/// File › Open in New Tab (⌥⌘O) on the focused selection: the context menus' own item (#5652, #2496). ⌘O is Open
/// Project, so selection-opens take the ⌘⌥O family.
struct FocusedOpenInNewTabButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        OpenInNewTabMenuItem(target: target)
            .keyboardShortcut("o", modifiers: [.command, .option])
        // The first of File's item verbs: "Select an item first" is said here, once.
        if let reason = ItemVerbs.openReason(target, action: target?.openInNewTab) {
            Text(reason)
        }
    }
}

/// File › Open in New Window (⇧⌥⌘O), the sibling of Open in New Tab.
struct FocusedOpenInNewWindowButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        OpenInNewWindowMenuItem(target: target)
            .keyboardShortcut("o", modifiers: [.command, .option, .shift])
        FocusedItemOrganiseButtons.reason(ItemVerbs.openReason(target, action: target?.openInNewWindow))
    }
}
