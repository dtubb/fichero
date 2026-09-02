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
/// With a `paneKindSwitcher` in the environment (injected per SLOT by the
/// pane row), the kind icon is a working menu — R3's mutation across kinds.
/// Without one (a pane hosted outside a switchable slot), it renders as a
/// plain label rather than a menu that lies.
struct PaneKindSelector<Lens: Hashable & Identifiable>: View {
    let kindTitle: String
    let kindIcon: String
    /// Injected by the pane slot: when present, the kind icon is a MENU that
    /// switches what the slot hosts (Daniel, 2026-08-23).
    @Environment(\.paneKindSwitcher) private var paneKindSwitcher
    let lenses: [Lens]
    let lensTitle: (Lens) -> String
    let lensIcon: (Lens) -> String
    /// Optional section grouping (title, members) — the library's view menu
    /// keeps its browse/dataset/canvas sections (Daniel, 2026-08-23). Empty →
    /// one flat list.
    var lensSections: [(String, [Lens])] = []
    /// ONE glyph in the identity capsule (Daniel, 2026-09-01: "the proxy icon
    /// and the kind icon appear twice — one icon"). The reader head carried a
    /// kind glyph AND a lens glyph a divider apart, both reading as "a page of
    /// text", right beside the breadcrumb's document icon. Panes that set this
    /// always render the merged rung — the kind icon IS the lens menu — which
    /// is the same collapse the narrowest width already performs, so no rung
    /// and no menu entry is lost.
    var collapsesKindIntoLens: Bool = false
    /// What the pane is actually SHOWING, named beside the glyph (Daniel,
    /// 2026-09-02: the reader head "never says WHAT is displayed — document
    /// content, or which artifact"). The lens TITLE is not always the answer:
    /// the Content lens can be pointed at a transcription, a translation or
    /// one named artifact, and all four look identical without this. nil =
    /// the pane has nothing more specific to say than its lens icon, and the
    /// selector renders exactly as it did before.
    var shownLabel: String?
    /// Extra rows appended to the LENS menu below a divider — the reader's
    /// "Showing" submenu of representations and artifacts (Daniel,
    /// 2026-09-02: the View menu "should gain a submenu listing the artifacts
    /// available for the current document"). `AnyView` deliberately: a fourth
    /// generic parameter on this type multiplies into every head that
    /// composes it, which is the #4331 stall class.
    var extraLensMenu: (() -> AnyView)?
    @Binding var lens: Lens

    var body: some View {
        if collapsesKindIntoLens {
            mergedSelector
        } else {
            adaptiveSelector
        }
    }

    @ViewBuilder
    private var adaptiveSelector: some View {
        // Adaptive (Daniel, 2026-08-23): when the pane is tight the lens
        // collapses to its ICON — the head can always be two glyphs on the
        // left, one crumb icon in the middle, one glyph on the right.
        ViewThatFits(in: .horizontal) {
            selectorRow(lensIconOnly: false)
            selectorRow(lensIconOnly: true)
            // Narrowest rung (Daniel, 2026-08-23): kind and lens COLLAPSE
            // into one control — the kind icon opens the lens menu. No
            // `shownLabel` here: this rung exists because the head ran out of
            // room, so it must stay the icon alone.
            mergedRung(namesWhatIsShown: false)
        }
    }

    /// One glyph, and — when the pane says what it is showing — its name
    /// beside it. Degrades to the glyph alone in a narrow pane.
    private var mergedSelector: some View {
        // AnyView per rung is LOAD-BEARING (the #4331 rule the breadcrumb
        // ladder documents): menu-bearing candidates compose deep.
        ViewThatFits(in: .horizontal) {
            AnyView(mergedRung(namesWhatIsShown: shownLabel != nil))
            AnyView(mergedRung(namesWhatIsShown: false))
        }
    }

    private func mergedRung(namesWhatIsShown: Bool) -> some View {
        // ponytail: the merged rung keeps the LENS menu; kind switching at
        // the narrowest width goes through the pane's right-click/full head.
        lensMenuContent {
            HStack(spacing: 4) {
                Label(kindTitle, systemImage: kindIcon)
                    .font(.callout.weight(.medium))
                    .labelStyle(.iconOnly)
                if namesWhatIsShown, let shownLabel {
                    Text(shownLabel)
                        .font(.callout)
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(maxWidth: PaneKindSelectorMetrics.shownLabelMaxWidth,
                               alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .help(shownLabel.map { "\(kindTitle) — showing \($0). Click to change." }
            ?? "\(kindTitle) — choose what this pane shows")
        .accessibilityLabel(shownLabel.map { "\(kindTitle), showing \($0)" } ?? kindTitle)
    }

    private func selectorRow(lensIconOnly: Bool) -> some View {
        HStack(spacing: 6) {
            kindControl

            Divider().frame(height: PaneHeadMetrics.dividerHeight)

            lensMenu(iconOnly: lensIconOnly)
        }
    }

    /// Icon ONLY (Daniel, 2026-08-23): the kind never spells its name. With
    /// a slot switcher present, clicking it changes what the slot hosts —
    /// the control that makes a pane's type mutable in place (R3).
    @ViewBuilder
    private var kindControl: some View {
        let label = Label(kindTitle, systemImage: kindIcon)
            .font(.callout.weight(.medium))
            .labelStyle(.iconOnly)
        if let paneKindSwitcher {
            Menu {
                ForEach(PaneSpec.Kind.allCases, id: \.rawValue) { kind in
                    Button {
                        paneKindSwitcher.switchKind(kind)
                    } label: {
                        Label(kind.title, systemImage: kind.icon)
                    }
                }
            } label: {
                label
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .accessibilityLabel("Pane kind: \(kindTitle) — click to change")
            .help("\(kindTitle) — click to change this pane")
        } else {
            label
                .accessibilityLabel("Pane kind: \(kindTitle)")
                .help(kindTitle)
        }
    }

    private func lensMenu(iconOnly: Bool) -> some View {
        lensMenuContent {
            // Two literal branches, not an erased LabelStyle: calling
            // makeBody by hand read Label's internal spacing environment
            // outside an installed view (the Optional<CGFloat> fault storm,
            // 2026-08-23 live).
            if iconOnly {
                Label(lensTitle(lens), systemImage: lensIcon(lens))
                    .font(.callout)
                    .labelStyle(.iconOnly)
            } else {
                Label(lensTitle(lens), systemImage: lensIcon(lens))
                    .font(.callout)
                    .labelStyle(.titleAndIcon)
            }
        }
        .accessibilityLabel("View: \(lensTitle(lens))")
        .help("Choose what this pane shows")
    }

    private func lensMenuContent<L: View>(@ViewBuilder label: () -> L) -> some View {
        Menu {
                if lensSections.isEmpty {
                    Picker("View", selection: $lens) {
                        ForEach(lenses) { option in
                            Label(lensTitle(option), systemImage: lensIcon(option)).tag(option)
                        }
                    }
                    .pickerStyle(.inline)
                } else {
                    // Plain checkmarked Buttons, not inline Pickers: each
                    // inline Picker drew its OWN separator chrome inside the
                    // section, so every group rendered with a stray line
                    // under its header (Daniel, 2026-08-29: "a line between
                    // each group — weird").
                    ForEach(Array(lensSections.enumerated()), id: \.offset) { _, section in
                        Section(section.0) {
                            ForEach(section.1) { option in
                                Button {
                                    lens = option
                                } label: {
                                    if lens == option {
                                        Label(lensTitle(option), systemImage: "checkmark")
                                    } else {
                                        Label(lensTitle(option), systemImage: lensIcon(option))
                                    }
                                }
                            }
                        }
                    }
                }
                // The pane's own extra rows — the reader's "Showing" submenu
                // of representations and artifacts. Below a divider, so the
                // lens list above stays the same list it always was.
                if let extraLensMenu {
                    Divider()
                    extraLensMenu()
                }
        } label: {
            label()
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }
}

/// The selector's own metric, kept out of `PaneHeadMetrics` because it is a
/// property of this control rather than of the head's capsule geometry.
enum PaneKindSelectorMetrics {
    /// How much room the "what is shown" name may take before it truncates.
    /// Wide enough for "Transcription — claude-opus-5", narrow enough that it
    /// cannot squeeze the breadcrumb out of the head.
    static let shownLabelMaxWidth: CGFloat = 190
}
