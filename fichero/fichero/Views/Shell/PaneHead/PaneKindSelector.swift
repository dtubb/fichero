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
    /// This slot's own kind (#4880: every kind chooser ticks its current row —
    /// the row list already covers every real kind via `PaneSpec.Kind.
    /// selectableKinds`, so the control needs to know which one it IS to mark
    /// it).
    let currentKind: PaneSpec.Kind
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

    // #4880: ONE ladder for every kind — Reader used to render a single
    // merged icon (`collapsesKindIntoLens`, deleted) instead of this. That
    // meant Reader's kind and view were one menu while Library/Preview kept
    // two, and Reader had no separate view chooser to move its views into.
    // The narrowest rung below still merges kind+lens into one icon when
    // there truly isn't room for two — that is a WIDTH fallback every kind
    // shares, not a per-kind mode.
    var body: some View {
        adaptiveSelector
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

    /// The narrowest-width fallback: kind and lens collapse into ONE icon
    /// that opens ONE menu (the maintainer, 2026-09-01 "one icon" ruling), used by
    /// every kind once its normal two-control row no longer fits.
    private func mergedRung(namesWhatIsShown: Bool) -> some View {
        // Folds in the real pane-kind switch (#4705) so the narrowest rung
        // loses no capability versus the normal two-control row above it.
        lensMenuContent(includeKindSwitcher: true) {
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

    /// Icon plus chevron (#4880: "a bare icon with no chevron does not look
    /// like a menu at all"). With a slot switcher present, clicking it
    /// changes what the slot hosts — the control that makes a pane's type
    /// mutable in place (R3). Every row carries its icon AND a tick on the
    /// pane's current kind (`kindRow`).
    @ViewBuilder
    private var kindControl: some View {
        let label = Label(kindTitle, systemImage: kindIcon)
            .font(.callout.weight(.medium))
            .labelStyle(.iconOnly)
        if let paneKindSwitcher {
            Menu {
                // Real kinds only (#4705): `.inspector`/`.chat` are
                // placeholder leaves until increments 6/7 give them content.
                ForEach(PaneSpec.Kind.selectableKinds, id: \.rawValue) { kind in
                    Button {
                        paneKindSwitcher.switchKind(kind)
                    } label: {
                        kindRow(kind)
                    }
                }
            } label: {
                label
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .accessibilityLabel("Pane kind: \(kindTitle) — click to change")
            .help("\(kindTitle) — click to change this pane")
        } else {
            label
                .accessibilityLabel("Pane kind: \(kindTitle)")
                .help(kindTitle)
        }
    }

    /// One kind row: icon, title, and a trailing tick when it is the pane's
    /// current kind (#4880) — shared by the kind chooser and the narrowest
    /// rung's folded-in kind switch, so the two can never show the tick
    /// differently.
    private func kindRow(_ kind: PaneSpec.Kind) -> some View {
        Label {
            HStack(spacing: 4) {
                Text(kind.title)
                if kind == currentKind {
                    Image(systemName: "checkmark")
                }
            }
        } icon: {
            Image(systemName: kind.icon)
        }
    }

    /// One lens row: icon, title, and a trailing tick on the current lens
    /// (#4880) — shared by the sectioned lens menu below.
    private func lensRow(_ option: Lens) -> some View {
        Label {
            HStack(spacing: 4) {
                Text(lensTitle(option))
                if option == lens {
                    Image(systemName: "checkmark")
                }
            }
        } icon: {
            Image(systemName: lensIcon(option))
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
                // Icon plus label plus, when the pane says what it is
                // showing, its name too (#4880's "icon plus label plus
                // chevron" — the chevron is the enclosing Menu's own).
                HStack(spacing: 4) {
                    Label(lensTitle(lens), systemImage: lensIcon(lens))
                        .font(.callout)
                        .labelStyle(.titleAndIcon)
                    if let shownLabel {
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
        }
        .accessibilityLabel(shownLabel.map { "View: \(lensTitle(lens)), showing \($0)" }
            ?? "View: \(lensTitle(lens))")
        .help(shownLabel.map { "\(lensTitle(lens)) — showing \($0). Click to change." }
            ?? "Choose what this pane shows")
    }

    private func lensMenuContent<L: View>(
        includeKindSwitcher: Bool = false,
        @ViewBuilder label: () -> L
    ) -> some View {
        Menu {
                // Folded in only by the narrowest rung: the normal row
                // already has its own separate `kindControl` menu, so
                // adding this here too would duplicate the switch rather
                // than restore parity (#4705).
                if includeKindSwitcher, let paneKindSwitcher {
                    Section(kindTitle) {
                        ForEach(PaneSpec.Kind.selectableKinds, id: \.rawValue) { kind in
                            Button {
                                paneKindSwitcher.switchKind(kind)
                            } label: {
                                kindRow(kind)
                            }
                        }
                    }
                    Divider()
                }
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
                                    // Icon AND tick together (#4880: "every
                                    // row with its icon, a tick on the
                                    // current view") — the checkmark no
                                    // longer replaces the row's own glyph.
                                    lensRow(option)
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
