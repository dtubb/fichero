import SwiftUI

/// The Segment menu (#5157): set kind, direction, text-or-furniture -- and, where the host can ask
/// for a code, language and script -- on every selected segment at once. ONE menu for every place
/// that offers these verbs (the Inspector, the Source view's Edit Segments context menu); each choice
/// becomes one audited `segment.update_many` through `SegmentEdit.set`, so one ⌘Z undoes it.
struct SegmentAttributeMenu: View {
    let apply: (SegmentEdit.Attribute) -> Void
    /// Offer "Language…" / "Script…", which need a code typed: only where the host can ask for one.
    var askForCode: ((CodeKind) -> Void)?
    /// The region types the engine offers for this page; the Type submenu shows only when there are some.
    var types: [RegionTypeChoice] = []

    enum CodeKind { case language, script }

    /// The kinds offered by name; kinds are open (`source.segment.open-kinds`), these are the ladder's.
    static let kinds = ["region", "line", "word", "character"]

    var body: some View {
        Menu("Segment") { Items(apply: apply, askForCode: askForCode, types: types) }
    }

    /// The menu's items on their own: the menu bar's Segment menu lists them at its top level (#5229).
    struct Items: View {
        let apply: (SegmentEdit.Attribute) -> Void
        var askForCode: ((CodeKind) -> Void)?
        var types: [RegionTypeChoice] = []

        var body: some View {
            if !types.isEmpty {
                Menu("Type") {
                    ForEach(Array(types.enumerated()), id: \.element.id) { index, type in
                        typeButton(type, index: index)
                    }
                }
            }
            Menu("Kind") {
                ForEach(SegmentAttributeMenu.kinds, id: \.self) { kind in
                    Button(kind.capitalized) { apply(.kind(kind)) }
                }
            }
            Menu("Direction") {
                ForEach(SegmentEdit.directions, id: \.self) { direction in
                    Button(SegmentEdit.directionName(direction)) { apply(.direction(direction)) }
                }
            }
            Button("Mark as Text") { apply(.furniture(false)) }
            Button("Not Part of the Text") { apply(.furniture(true)) }
            if let askForCode {
                Divider()
                Button("Language…") { askForCode(.language) }
                Button("Script…") { askForCode(.script) }
            }
        }

        /// The first nine types take Ctrl-Option-1 to 9 (`segment-editor.type-by-key`).
        @ViewBuilder private func typeButton(_ type: RegionTypeChoice, index: Int) -> some View {
            let button = Button(type.label) { apply(.type(type.label)) }.help(type.zoneName ?? type.label)
            if index < 9, let key = "123456789".dropFirst(index).first {
                button.keyboardShortcut(KeyEquivalent(key), modifiers: [.control, .option])
            } else {
                button
            }
        }
    }
}

#if DEBUG
#Preview("The Segment menu") {
    SegmentAttributeMenu(apply: { _ in }, askForCode: { _ in })
        .padding()
}
#endif
