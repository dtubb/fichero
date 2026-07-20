import OSLog
import SwiftUI

#if canImport(AppKit)
import AppKit
#endif

// MARK: - Undo (audited actions)

/// ⌘Z — undo the last audited action via `POST /api/actions/audit/{id}/undo` (#2015).
///
/// MVP **single-level** undo: it reverses the most recent action recorded in the
/// shared `LastAction` holder (seeded today by the entity-merge button), then
/// clears the holder so a repeated ⌘Z can't double-undo the same audit row.
/// The observable change stream propagates the reversed state back into the open
/// views, so there is no manual refresh here.
///
/// Multi-level undo — a per-window stack that walks the `/api/actions/audit`
/// log row by row — is a deliberate follow-up. This replaces SwiftUI's default
/// `.undoRedo` menu items so there is exactly one "Undo", and so the view-local
/// `UndoManager` isn't fighting the audited backend undo.
/// View-menu "Back" — steps the focused window's navigation history back one
/// entry (#3581). Mirrors the content-column toolbar button's ⌘' shortcut and
/// enabled state; disabled when there's no focused window or nothing to go back to.
struct NavigateBackButton: View {
    @FocusedValue(\.navigateBackAction) private var navigateBackAction

    var body: some View {
        Button("Back") {
            navigateBackAction?.run()
        }
        .keyboardShortcut("'", modifiers: [.command])
        .disabled(!(navigateBackAction?.isEnabled ?? false))
    }
}

/// View-menu "Forward" — the ⌘⇧' counterpart to `NavigateBackButton` (#3581).
struct NavigateForwardButton: View {
    @FocusedValue(\.navigateForwardAction) private var navigateForwardAction

    var body: some View {
        Button("Forward") {
            navigateForwardAction?.run()
        }
        .keyboardShortcut("'", modifiers: [.command, .shift])
        .disabled(!(navigateForwardAction?.isEnabled ?? false))
    }
}

struct UndoLastActionButton: View {
    /// The active library's audited-action holder (#3444 — per library, not a
    /// process-global singleton). Reading `.actionName`/`.auditId` in the body
    /// registers an @Observable dependency, so the menu item's title + enabled
    /// state track the last recorded action without manual republishing.
    private var lastAction: LastAction? {
        LibraryManager.shared.globalLibrary?.actionsService.lastAction
    }
    /// The active library's audit log — the source of truth for multi-level undo
    /// (#3444). ⌘Z walks it row by row instead of only reversing the single
    /// last-recorded action.
    private var auditStore: AuditStore? {
        LibraryManager.shared.globalLibrary?.auditStore
    }
    @FocusedValue(\.navigationUndoAction) private var navigationUndoAction

    private var logger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "ActionUndo")
    }

    var body: some View {
        Button(undoTitle) {
            performUndo()
        }
        .keyboardShortcut("z", modifiers: .command)
        .disabled(!isEnabled)
    }

    /// "Undo Merge" when the next undoable action is known, plain "Undo"
    /// otherwise. Prefers the audit log's next target (multi-level, #3444);
    /// falls back to the last-recorded action before the log has loaded.
    private var undoTitle: String {
        if navigationUndoAction != nil {
            return "Undo"
        }
        let name = auditStore?.nextUndoableEntry?.actionName ?? lastAction?.actionName
        guard let name else { return "Undo" }
        return "Undo \(Self.menuLabel(for: name))"
    }

    private var isEnabled: Bool {
        navigationUndoAction?.isEnabled == true
            || auditStore?.nextUndoableEntry != nil
            || lastAction?.auditId != nil
    }

    /// `"entity.merge"` → `"Merge"`. Falls back to the raw name if unverbed.
    private static func menuLabel(for actionName: String) -> String {
        let verb = actionName.split(separator: ".").last.map(String.init) ?? actionName
        guard let first = verb.first else { return verb }
        return first.uppercased() + verb.dropFirst()
    }

    private func performUndo() {
        if let navigationUndoAction, navigationUndoAction.isEnabled {
            navigationUndoAction.run()
            return
        }
        guard let auditStore else { return }
        Task {
            // Multi-level: walk the audit log and reverse the most-recent
            // still-undoable forward action. `undoLast()` loads the log if
            // needed and reloads after, so a repeated ⌘Z steps further back.
            let didUndo = await auditStore.undoLast()
            if didUndo {
                logger.info("⌘Z multi-level undo succeeded")
                // Keep the single-level signal in sync: once the log has no more
                // undoable forward actions, drop it so Undo disables cleanly.
                if auditStore.nextUndoableEntry == nil {
                    lastAction?.auditId = nil
                    lastAction?.actionName = nil
                }
            } else {
                // Nothing left to undo, or the reversal failed — clear the signal
                // and surface any message (raise-not-silent, #3302).
                lastAction?.auditId = nil
                lastAction?.actionName = nil
                logger.error("⌘Z undo found nothing to reverse or failed")
                if let message = auditStore.statusMessage, message != "Nothing to undo" {
                    presentUndoError(
                        NSError(
                            domain: "app.fichero.undo",
                            code: 0,
                            userInfo: [NSLocalizedDescriptionKey: message]
                        )
                    )
                }
            }
        }
    }

    private func presentUndoError(_ error: Error) {
        #if canImport(AppKit)
        let alert = NSAlert()
        alert.messageText = "Couldn't Undo"
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
        #endif
    }
}
