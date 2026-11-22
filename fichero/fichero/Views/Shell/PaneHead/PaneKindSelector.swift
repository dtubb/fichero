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
/// The kind choice is not here: it is Pane ▸ in the pane menu at the head's right (#6741).
struct PaneKindSelector<Lens: Hashable & Identifiable>: View {
    let kindTitle: String
    let kindIcon: String
    /// This slot's own kind (#4880; the tick now lives in the pane menu's Pane ▸ —
    /// the row list already covers every real kind via `PaneSpec.Kind.
    /// selectableKinds`, so the control needs to know which one it IS to mark
    /// it).
    let currentKind: PaneSpec.Kind
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
    /// #6458: the lens title in three forms (full, reader, lens name); the longest that fits is shown, the full form is the
    /// tooltip and accessibility label. nil = the title is the lens name plus `shownLabel`, as before.
    var titleForms: PaneTitleForms?
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
        BodyCount.tick("PaneKindSelector")
        return adaptiveSelector
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
        lensMenu(iconOnly: lensIconOnly)
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
            } else if let titleForms {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 3) {
                        titleLabel(titleForms.full)
                        if let symbol = titleForms.symbol {
                            Image(systemName: symbol).font(.caption)
                        }
                    }
                    titleLabel(titleForms.middle)
                    titleLabel(titleForms.short)
                }
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
        .accessibilityLabel(titleForms.map { "View: \($0.tooltip)" }
            ?? shownLabel.map { "View: \(lensTitle(lens)), showing \($0)" }
            ?? "View: \(lensTitle(lens))")
        .help(titleForms.map { "\($0.tooltip). Click to change." }
            ?? shownLabel.map { "\(lensTitle(lens)) — showing \($0). Click to change." }
            ?? "Choose what this pane shows")
    }

    private func titleLabel(_ form: String) -> some View {
        Label(form, systemImage: lensIcon(lens))
            .font(.callout)
            .labelStyle(.titleAndIcon)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
    }

    /// The rows of the view menu, shared by the head's chooser and the pane menu's View As ▸.
    @ViewBuilder
    private var lensMenuItems: some View {
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
    }

    private func lensMenuContent<L: View>(@ViewBuilder label: () -> L) -> some View {
        Menu {
            lensMenuItems
        } label: {
            label()
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }
}

/// A head's view chooser that hands its view list to the pane menu as View As ▸ (`panes.head.one-menu-button`).
@MainActor
protocol PaneViewChooser {
    var viewAsMenu: AnyView { get }
}

extension PaneKindSelector: PaneViewChooser {
    var viewAsMenu: AnyView { AnyView(Menu("View As") { lensMenuItems }) }
}

/// The selector's own metric, kept out of `PaneHeadMetrics` because it is a
/// property of this control rather than of the head's capsule geometry.
enum PaneKindSelectorMetrics {
    /// How much room the "what is shown" name may take before it truncates.
    /// Wide enough for "Transcription — claude-opus-5", narrow enough that it
    /// cannot squeeze the breadcrumb out of the head.
    static let shownLabelMaxWidth: CGFloat = 190
}
