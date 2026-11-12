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
    /// No text focus; the mounted image editor drops its last edit step
    /// (Daniel, 2026-08-31): while editing an image, ⌘Z means "undo that edit".
    case imageEdit
    /// No text focus; the key window's own step stack has a step a person took in
    /// this window (`undo.window`, ruled per window 2026-10-11, #5658).
    case windowStep
    /// Nothing to undo HERE — the menu item is disabled. Going Back is not an undo
    /// (`undo.edit-menu.never-navigates`), and another window's or another person's change
    /// is taken back from the history list, never by ⌘Z.
    case none
}

/// Pure focus→route policy. No AppKit, no view state: testable on its own.
enum UndoRoutingPolicy {
    /// - Parameters:
    ///   - isTextEditing: an editable text responder holds focus.
    ///   - textUndoAvailable: that responder's undo manager has something to undo.
    ///   - imageEditUndoEnabled: an image editor is mounted with a non-empty edit chain.
    ///   - windowUndoAvailable: the key window's steps can undo (none, while one of its calls is
    ///     out: `undo.window.in-flight`).
    static func route(
        isTextEditing: Bool,
        textUndoAvailable: Bool,
        imageEditUndoEnabled: Bool = false,
        windowUndoAvailable: Bool = false
    ) -> UndoRoute {
        // While a text editor has focus ⌘Z NEVER falls through to a project step.
        // An empty typing stack means "nothing to undo here".
        if isTextEditing {
            return textUndoAvailable ? .focusedTextEditor : .none
        }
        if imageEditUndoEnabled { return .imageEdit }
        if windowUndoAvailable { return .windowStep }
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

    /// The ⌘⇧Z counterpart to `canUndo`/`undo()` (menu audit 2026-09-17: Redo
    /// never existed, so a focused text editor's typing had no way back once
    /// undone).
    static var canRedo: Bool { editableTextView?.undoManager?.canRedo ?? false }

    static func redo() { editableTextView?.undoManager?.redo() }

    /// Hand ⌘A back to the editor that has focus (#4376) — the same
    /// give-it-back move `undo()` makes for ⌘Z.
    static func selectAll() { editableTextView?.selectAll(nil) }
    #else
    static var isEditing: Bool { false }
    static var canUndo: Bool { false }
    static func undo() {}
    static var canRedo: Bool { false }
    static func redo() {}
    static func selectAll() {}
    #endif
}

// MARK: - ⌘⇧Z (menu audit 2026-09-17)

/// Where ⌘⇧Z should land — the Redo counterpart of `UndoRoute`/`UndoRoutingPolicy`:
/// a focused text editor's typing, or the key window's steps (#5658). The image editor's
/// undo chain (#4409) has no recorded redo step, so that route is absent rather than faked.
enum RedoRoute: Equatable {
    /// A text editor has focus — its own undo manager owns ⌘⇧Z.
    case focusedTextEditor
    /// No text focus; the key window's step stack has a step to put back (#5658).
    case windowStep
    /// Nothing to redo — the menu item is disabled.
    case none
}

/// Pure focus→route policy, the same shape as `UndoRoutingPolicy`.
enum RedoRoutingPolicy {
    static func route(
        isTextEditing: Bool,
        textRedoAvailable: Bool,
        windowRedoAvailable: Bool = false
    ) -> RedoRoute {
        if isTextEditing {
            return textRedoAvailable ? .focusedTextEditor : .none
        }
        return windowRedoAvailable ? .windowStep : .none
    }
}

// MARK: - ⌘A (#4376)

/// Where ⌘A lands, decided by what currently has focus.
///
/// Same shape and same root cause as ⌘Z (#4354): a `.keyboardShortcut` on a
/// menu item is an NSMenuItem key equivalent, and AppKit matches key
/// equivalents BEFORE the event reaches the responder chain. A ⌘A claimed once
/// at app level would select library rows while the user is typing.
///
/// The `none` case is load-bearing and is NOT a failure: it disables this menu
/// item so the key equivalent falls through to the system's own Select All and
/// on to the responder chain — which is exactly what a focused WKWebView (the
/// reader) needs, since selecting its text is the web view's own job. The app
/// declines rather than guessing.
enum SelectAllRoute: Equatable {
    /// An editable text responder holds focus — its own select-all owns ⌘A.
    case focusedTextEditor
    /// The library pane holds focus — select every row it is showing.
    case libraryRows
    /// A selectable list in the inspector holds focus — select its rows.
    case inspectorList
    /// The sidebar holds focus — ⌘A is taken and does nothing: it never selects the sidebar's rows, and it is not left to
    /// fall through to the system, whose list would select them all (`ui.select-all.never-the-sidebar`, #6364).
    case sidebarIgnored
    /// The preview holds focus over an image — select the WHOLE image, which
    /// is what the marquee's unit rect means.
    case previewImage
    /// Nobody the app speaks for holds focus. Disabled; let it fall through.
    case none
}

/// A surface that can answer ⌘A with rows, once text focus has been ruled out.
///
/// The publications are scene-scoped (`focusedSceneValue`), so more than one
/// can be live at the same instant — the library publishes whenever a library
/// pane is in the focused scene, whether or not the pointer went to the
/// inspector. Precedence therefore cannot be inferred from "who published"; it
/// has to come from which PANE holds focus, which is why `route` takes the
/// pane rather than a set of booleans.
enum SelectAllSurface: Equatable {
    case libraryRows
    case inspectorList
    /// The sidebar holds focus. It has no rows to select: ⌘A over it is ignored (`ui.select-all.never-the-sidebar`, #6364).
    case sidebar
    case previewImage
}

/// Pure focus→route policy. No AppKit, no view state: testable on its own.
enum SelectAllRoutingPolicy {
    /// - Parameters:
    ///   - isTextEditing: an editable text responder holds focus.
    ///   - focusedSurface: the surface that both HOLDS focus and has rows to
    ///     select, or nil. Nil covers every falling-through case — no focus the
    ///     app speaks for, or a focused surface whose list is empty — and both
    ///     must decline rather than fire an empty selection.
    static func route(
        isTextEditing: Bool,
        focusedSurface: SelectAllSurface?
    ) -> SelectAllRoute {
        // Text focus wins outright. "Select all" while typing means the text,
        // and it must never reach past the caret to the rows behind it.
        if isTextEditing { return .focusedTextEditor }
        switch focusedSurface {
        case .libraryRows: return .libraryRows
        case .inspectorList: return .inspectorList
        case .sidebar: return .sidebarIgnored
        case .previewImage: return .previewImage
        case nil: return .none
        }
    }
}

// MARK: - Select All (#4376)

/// ⌘A — Select All, routed by what actually has focus.
///
/// The library published a `librarySelectAll` focused action but nothing in the
/// menu ever consumed it, and the app declared no ⌘A of its own. So ⌘A went to
/// the system Select All, down the responder chain, to a SwiftUI
/// `ScrollView`+`LazyVStack` that implements no `selectAll(_:)` — and did
/// nothing at all. The action existed; the command never reached it.
///
/// This is the ⌘Z shape from #4354, reusing its `FocusedTextResponder` probe
/// rather than inventing a second answer to "what has focus". One place decides;
/// each command asks it.
///
/// The disabled case matters as much as the enabled ones: when neither a text
/// editor nor the library holds focus — the reader, which is a WebKit surface —
/// this item disables so the key equivalent falls through to the system Select
/// All and the web view selects its own text. Claiming ⌘A there and guessing
/// would be the #4354 bug in a new costume.
@MainActor
struct SelectAllButton: View {
    @FocusedValue(\.librarySelectAll) private var librarySelectAll
    @FocusedValue(\.inspectorSelectAll) private var inspectorSelectAll
    @FocusedValue(\.focusedPaneKind) private var focusedPane
    @FocusedValue(\.previewSelectAll) private var previewSelectAll

    var body: some View {
        Button("Select All") {
            performSelectAll()
        }
        .keyboardShortcut("a", modifiers: .command)
        .disabled(route == .none)
    }

    /// Recomputed on every body evaluation — which is when AppKit rebuilds and
    /// validates the menu, immediately before display and before a key
    /// equivalent fires. That is the moment the focus probe has to be read.
    private var route: SelectAllRoute {
        SelectAllRoutingPolicy.route(
            isTextEditing: FocusedTextResponder.isEditing,
            focusedSurface: focusedSurface
        )
    }

    /// The surface that both HOLDS focus and has rows to select.
    ///
    /// Both halves are required. A publication alone is not focus — these are
    /// scene-scoped, so the library's is live whenever a library pane is on
    /// screen — and focus alone is not rows, since an empty list must decline
    /// so the key equivalent can fall through.
    private var focusedSurface: SelectAllSurface? {
        SelectAllSidebarGuard.surface(
            sidebarHoldsKeyboardFocus: SidebarKeyboardFocus.isSidebarFocused,
            paneSurface: paneSurface
        )
    }

    /// The surface the pane-focus hint names. The hint comes only from taps, so it can name
    /// another pane (or none) while the sidebar outline holds the keyboard; `focusedSurface`
    /// checks the keyboard first.
    private var paneSurface: SelectAllSurface? {
        switch focusedPane {
        case .inspector:
            return inspectorSelectAll?.isEnabled == true ? .inspectorList : nil
        case .sidebar:
            // Focus alone is enough here: the sidebar is never selected whole (#6364), so the chord is taken and ignored
            // rather than declined, which would let the system's own select-all take the sidebar's rows.
            return .sidebar
        case .preview:
            return previewSelectAll?.isEnabled == true ? .previewImage : nil
        case .reading:
            // DELIBERATELY nil: the reader is WebKit and selecting its text is
            // the web view's own job, so this route declines and the key
            // equivalent falls through. Spelled out rather than left to the
            // default branch, because "the reader works" was previously an
            // accident of the library's enablement rather than a decision.
            return nil
        case .segments:
            // DELIBERATELY nil: the Segments pane's list is a SwiftUI List whose own selection answers
            // ⌘A; the library must not take it just because it is the default owner (#4942).
            return nil
        default:
            // The library is the default owner, as it was before the inspector
            // could answer: no pane hint at all still means the library, which
            // is what keeps a plain library window behaving exactly as it did.
            return librarySelectAll?.isEnabled == true ? .libraryRows : nil
        }
    }

    private func performSelectAll() {
        switch route {
        case .none:
            return
        case .focusedTextEditor:
            // Hand it back to the editor that has focus — the shape the
            // responder chain would have produced if a key equivalent had not
            // matched first (#4354/#4376).
            FocusedTextResponder.selectAll()
        case .libraryRows:
            librarySelectAll?.run()
        case .inspectorList:
            inspectorSelectAll?.run()
        case .sidebarIgnored:
            return
        case .previewImage:
            previewSelectAll?.run()
        }
    }
}

/// ⌘A never selects the whole sidebar (`ui.select-all.never-the-sidebar`, #6364). When the
/// sidebar's outline holds the keyboard, ⌘A is taken and ignored, whatever the tap-based pane
/// hint says: a hint naming another pane, or none, let Select All disable itself, and ⌘A then fell
/// through to the system's Select All, which the outline answers by selecting every project,
/// folder and workflow.
enum SelectAllSidebarGuard {
    static func surface(sidebarHoldsKeyboardFocus: Bool, paneSurface: SelectAllSurface?) -> SelectAllSurface? {
        sidebarHoldsKeyboardFocus ? .sidebar : paneSurface
    }
}

/// Whether the key window's first responder sits inside the sidebar's list: the view carrying
/// `SidebarAccessibilityID.list`, or one of its subviews. AppKit only; false elsewhere.
@MainActor
enum SidebarKeyboardFocus {
    static var isSidebarFocused: Bool {
        #if canImport(AppKit)
        guard let responder = NSApp.keyWindow?.firstResponder as? NSView else { return false }
        return sequence(first: responder, next: \.superview)
            .contains { $0.accessibilityIdentifier() == SidebarAccessibilityID.list }
        #else
        return false
        #endif
    }
}
