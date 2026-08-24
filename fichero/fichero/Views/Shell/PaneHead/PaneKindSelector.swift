import SwiftUI

// MARK: - The two-level selector (R3)

/// Pane KIND, then the LENS within it — the control that makes a pane's type
/// mutable in place.
///
/// Two menus rather than one flat list, because a lens is meaningless without
/// its kind: "Map" means the reader's entity map here and the dataset's geo
/// view there, and a single list of every lens in the app would be twenty rows
/// that only make sense in pairs.
///
/// The kind menu is a placeholder in step 1 — only the Reader adopts the head
/// so far, so it renders the current kind without offering a change. R3's
/// mutation across kinds lands when the other panes adopt, and stubbing the
/// menu now would be a control that lies.
struct PaneKindSelector<Lens: Hashable & Identifiable>: View {
    let kindTitle: String
    let kindIcon: String
    let lenses: [Lens]
    let lensTitle: (Lens) -> String
    let lensIcon: (Lens) -> String
    /// Optional section grouping (title, members) — the library's view menu
    /// keeps its browse/dataset/canvas sections (Daniel, 2026-08-23). Empty →
    /// one flat list.
    var lensSections: [(String, [Lens])] = []
    @Binding var lens: Lens

    var body: some View {
        HStack(spacing: 6) {
            // Icon ONLY (Daniel, 2026-08-23): the kind never spells its name —
            // "no need to say reader or library, that can be icons". The name
            // survives for assistive tech and the hover help.
            Label(kindTitle, systemImage: kindIcon)
                .font(.callout.weight(.medium))
                .labelStyle(.iconOnly)
                .accessibilityLabel("Pane kind: \(kindTitle)")
                .help(kindTitle)

            Divider().frame(height: PaneHeadMetrics.dividerHeight)

            Menu {
                if lensSections.isEmpty {
                    Picker("View", selection: $lens) {
                        ForEach(lenses) { option in
                            Label(lensTitle(option), systemImage: lensIcon(option)).tag(option)
                        }
                    }
                    .pickerStyle(.inline)
                } else {
                    ForEach(Array(lensSections.enumerated()), id: \.offset) { _, section in
                        Section(section.0) {
                            Picker("View", selection: $lens) {
                                ForEach(section.1) { option in
                                    Label(lensTitle(option), systemImage: lensIcon(option)).tag(option)
                                }
                            }
                            .pickerStyle(.inline)
                        }
                    }
                }
            } label: {
                Label(lensTitle(lens), systemImage: lensIcon(lens))
                    .font(.callout)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .accessibilityLabel("View: \(lensTitle(lens))")
            .help("Choose what this pane shows")
        }
    }
}
