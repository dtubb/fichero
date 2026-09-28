import SwiftUI

/// The Segment menu (#5157): set kind, direction, text-or-furniture -- and, where the host can ask
/// for a code, language and script -- on every selected segment at once. ONE menu for every place
/// that offers these verbs (the Inspector, the Source view's Edit Segments context menu); each choice
/// becomes one audited `segment.update_many` through `SegmentEdit.set`, so one ⌘Z undoes it.
struct SegmentAttributeMenu: View {
    let apply: (SegmentEdit.Attribute) -> Void
    /// Offer "Language…" / "Script…", which need a code typed: only where the host can ask for one.
    var askForCode: ((CodeKind) -> Void)?

    enum CodeKind { case language, script }

    /// The kinds offered by name; kinds are open (`source.segment.open-kinds`), these are the ladder's.
    static let kinds = ["region", "line", "word", "character"]

    var body: some View {
        Menu("Segment") {
            Menu("Kind") {
                ForEach(Self.kinds, id: \.self) { kind in
                    Button(kind.capitalized) { apply(.kind(kind)) }
                }
            }
            Menu("Direction") {
                ForEach(SegmentEdit.directions, id: \.self) { direction in
                    Button(SegmentEdit.directionName(direction)) { apply(.direction(direction)) }
                }
            }
            Button("Mark as Text") { apply(.furniture(false)) }
            Button("Mark as Furniture") { apply(.furniture(true)) }
            if let askForCode {
                Divider()
                Button("Language…") { askForCode(.language) }
                Button("Script…") { askForCode(.script) }
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
