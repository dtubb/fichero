import SwiftUI

#if canImport(AppKit)
import AppKit
#endif

/// Where ⌘Z lands, decided by what currently has focus (#4354).
///
/// The Edit menu replaces `.undoRedo` with the audited-action Undo, and a
/// command-Z `.keyboardShortcut` on a menu item is a key equivalent — AppKit
/// matches key equivalents BEFORE the event reaches the responder chain. Without a
/// route decision the app-level undo swallows every ⌘Z, so typing a sentence and
/// pressing ⌘Z reverted an unrelated move / delete / workflow result instead of
/// the typing. That is a data-integrity bug, not a cosmetic one.
enum UndoRoute: Equatable {
    /// A text editor has focus — its own undo manager owns ⌘Z.
    case focusedTextEditor
    /// No text focus; the focused window's navigation history handles it.
    case navigation
    /// No text focus; the audited backend action log handles it.
    case auditedAction
    /// Nothing to undo — the menu item is disabled.
    case none
}

/// Pure focus→route policy. No AppKit, no view state: testable on its own.
enum UndoRoutingPolicy {
    /// - Parameters:
    ///   - isTextEditing: an editable text responder holds focus.
    ///   - textUndoAvailable: that responder's undo manager has something to undo.
    ///   - navigationUndoEnabled: the focused window can step navigation back.
    ///   - hasAuditedUndo: the audit log has a reversible forward action.
    static func route(
        isTextEditing: Bool,
        textUndoAvailable: Bool,
        navigationUndoEnabled: Bool,
        hasAuditedUndo: Bool
    ) -> UndoRoute {
        // While a text editor has focus ⌘Z NEVER falls through to a
        // document/library undo. An empty typing stack means "nothing to undo
        // here", not "go revert the last import".
        if isTextEditing {
            return textUndoAvailable ? .focusedTextEditor : .none
        }
        if navigationUndoEnabled { return .navigation }
        if hasAuditedUndo { return .auditedAction }
        return .none
    }
}

/// The AppKit first-responder probe behind `UndoRoutingPolicy`'s text inputs.
/// Cross-platform stubs on iOS, where there is no app-level ⌘Z menu item.
@MainActor
enum FocusedTextResponder {
    #if canImport(AppKit)
    /// The key window's first responder when it is an *editable* text view —
    /// the field editor for `TextField`, the backing view for `TextEditor` and
    /// `MacPlainTextEditor`. A selectable-but-not-editable text view is not an
    /// editing session and must not block the library undo.
    private static var editableTextView: NSTextView? {
        guard let responder = NSApp.keyWindow?.firstResponder as? NSTextView,
              responder.isEditable else { return nil }
        return responder
    }

    static var isEditing: Bool { editableTextView != nil }

    static var canUndo: Bool { editableTextView?.undoManager?.canUndo ?? false }

    static func undo() { editableTextView?.undoManager?.undo() }
    #else
    static var isEditing: Bool { false }
    static var canUndo: Bool { false }
    static func undo() {}
    #endif
}
