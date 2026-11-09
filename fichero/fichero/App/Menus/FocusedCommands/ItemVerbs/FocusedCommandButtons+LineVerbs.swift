import SwiftUI

// MARK: - A line's and a segment's verbs, one component each (#5652 slice 4, group 3)

// Correct This Line…, Open (a segment that holds others) and Create Named Order are ONE item each: the Reader's
// line rows, the Order list and the Segments pictures render them on their own row, and Page › Segments renders them
// on the focused list's selection (`LineVerbsTarget`), each disabled with its reason under it.

/// What a line or segment list offers on its selection. Equatable on what the menu shows, never on the closures.
struct LineVerbsTarget: Equatable {
    /// The selected segment, when there is exactly one.
    var segment: Segment?
    var correct: (@MainActor () -> Void)?
    var open: (@MainActor () -> Void)?
    var createNamedOrder: (@MainActor () -> Void)?
    /// Delete the selected lines (`source.editor.delete-selected-lines`): one audited batch, one ⌘Z.
    var delete: (@MainActor () -> Void)?
    /// Edit the selected line's words in place (Return, Finder style; Step 1.25).
    var rename: (@MainActor () -> Void)?
    /// Show the selection in the Preview (double-click).
    var reveal: (@MainActor () -> Void)?
    /// Move the selected row in the order; nil when the list has no order to move in.
    var move: (@MainActor (ReadingOrderMove.Step) -> Void)?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.segment?.id == rhs.segment?.id && lhs.segment?.kind == rhs.segment?.kind
            && (lhs.correct != nil) == (rhs.correct != nil) && (lhs.open != nil) == (rhs.open != nil)
            && (lhs.createNamedOrder != nil) == (rhs.createNamedOrder != nil)
            && (lhs.delete != nil) == (rhs.delete != nil) && (lhs.rename != nil) == (rhs.rename != nil)
            && (lhs.reveal != nil) == (rhs.reveal != nil) && (lhs.move != nil) == (rhs.move != nil)
    }
}

extension FocusedValues {
    /// The focused line or segment list's selection (the Order list, the Reader's selected line, the pictures).
    @Entry var lineVerbs: LineVerbsTarget?
}

enum LineVerbs {
    static let correctTitle = "Correct This Line…"
    static let createNamedOrderTitle = "Create Named Order"
    static let deleteTitle = "Delete Lines"
    static let renameTitle = "Rename"
    static let revealTitle = "Show in Preview"

    static func renameReason(_ target: LineVerbsTarget?) -> String? {
        target?.rename == nil ? "Select one line in the Order list" : nil
    }

    static func revealReason(_ target: LineVerbsTarget?) -> String? {
        target?.reveal == nil ? "Select a segment in the Order list" : nil
    }

    static func moveReason(_ target: LineVerbsTarget?) -> String? {
        target?.move == nil ? "Select a row in a named order" : nil
    }

    static func deleteReason(_ target: LineVerbsTarget?) -> String? {
        target?.delete == nil ? "Select a line in the Reader or the Order list" : nil
    }

    static func correctReason(_ target: LineVerbsTarget?) -> String? {
        guard let segment = target?.segment else { return "Select a line in the Reader or the Order list" }
        if !CorrectLine.offers(segment) { return "Only a line can be corrected" }
        return target?.correct == nil ? "Select the line in the Reader or the Order list" : nil
    }

    static func openReason(_ target: LineVerbsTarget?) -> String? {
        guard target?.segment != nil else { return "Select a segment that holds others" }
        return target?.open == nil ? "This segment holds nothing to open" : nil
    }

    static func createNamedOrderReason(_ target: LineVerbsTarget?) -> String? {
        target?.createNamedOrder == nil ? "Show a page with no named order in the Order list" : nil
    }
}

// MARK: - The items

struct CorrectLineMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        Button(LineVerbs.correctTitle) { target?.correct?() }
            .help("Type what this line says, as your reading")
            .disabled(LineVerbs.correctReason(target) != nil)
    }
}

struct OpenSegmentMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        Button { target?.open?() } label: { Label(ItemVerbs.openTitle, systemImage: "arrow.up.forward.app") }
            .disabled(LineVerbs.openReason(target) != nil)
    }
}

struct DeleteLinesMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        Button(LineVerbs.deleteTitle) { target?.delete?() }
            .help("Delete the selected lines; \u{2318}Z brings them back")
            .disabled(LineVerbs.deleteReason(target) != nil)
    }
}

struct RenameMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        // No chord here: Return belongs to the list (a menu key equivalent would take it from every text field).
        Button(LineVerbs.renameTitle) { target?.rename?() }
            .help("Edit this line's words in place (Return)")
            .disabled(LineVerbs.renameReason(target) != nil)
    }
}

struct RevealMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        Button(LineVerbs.revealTitle) { target?.reveal?() }
            .help("Select it and zoom the Preview to it (double-click)")
            .disabled(LineVerbs.revealReason(target) != nil)
    }
}

/// Move Up, Down, to Start and to End: the list's own buttons and ⌥⌘ keys, as items (no second chord set).
struct MoveRowMenuItems: View {
    let target: LineVerbsTarget?

    var body: some View {
        Menu("Move") {
            ForEach(Self.steps, id: \.title) { item in
                Button(item.title) { target?.move?(item.step) }
            }
        }
        .disabled(LineVerbs.moveReason(target) != nil)
    }

    private static let steps: [(title: String, step: ReadingOrderMove.Step)] = [
        ("Move Up", .upward), ("Move Down", .downward), ("Move to Start", .toStart), ("Move to End", .toEnd)
    ]
}

struct CreateNamedOrderMenuItem: View {
    let target: LineVerbsTarget?

    var body: some View {
        Button(LineVerbs.createNamedOrderTitle) { target?.createNamedOrder?() }
            .disabled(LineVerbs.createNamedOrderReason(target) != nil)
    }
}

// MARK: - The menu bar (Page › Segments)

struct FocusedLineVerbButtons: View {
    @FocusedValue(\.lineVerbs) private var target

    var body: some View {
        RenameMenuItem(target: target)
        if let reason = LineVerbs.renameReason(target) { Text(reason) }
        RevealMenuItem(target: target)
        MoveRowMenuItems(target: target)
        if let reason = LineVerbs.moveReason(target) { Text(reason) }
        CorrectLineMenuItem(target: target)
        if let reason = LineVerbs.correctReason(target) { Text(reason) }
        OpenSegmentMenuItem(target: target)
        if target != nil, let reason = LineVerbs.openReason(target) { Text(reason) }
        CreateNamedOrderMenuItem(target: target)
        if let reason = LineVerbs.createNamedOrderReason(target) { Text(reason) }
        DeleteLinesMenuItem(target: target)
        if let reason = LineVerbs.deleteReason(target) { Text(reason) }
    }
}
