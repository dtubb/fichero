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

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.segment?.id == rhs.segment?.id && lhs.segment?.kind == rhs.segment?.kind
            && (lhs.correct != nil) == (rhs.correct != nil) && (lhs.open != nil) == (rhs.open != nil)
            && (lhs.createNamedOrder != nil) == (rhs.createNamedOrder != nil)
            && (lhs.delete != nil) == (rhs.delete != nil)
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
