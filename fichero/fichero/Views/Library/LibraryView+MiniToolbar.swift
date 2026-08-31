import SwiftUI

// MARK: - Library mini toolbar (#4407 / #4374 finding 3)

/// The controls that act on the LIBRARY LIST, in one bar over the library pane.
///
/// The rule this encodes: **a control lives with the surface it acts on.**
/// Window chrome is for things that act on the window. Search, sort and filter
/// all act on the library list, so they sit above that list, resize with that
/// pane, and go away when the pane does.
///
/// All three were window-level before. The search field was the loudest case:
/// `.searchable` + `.searchScopes` were attached to the whole
/// `NavigationSplitView`, so the Ask/Keyword scope selector rendered as a bar
/// spanning the library, the preview and the reader together — a control whose
/// placement claimed window scope while it filtered one list. The reader's own
/// find bar sat inside the reader in the same screenshot, correctly scoped,
/// which is what made the mismatch obvious. That bar is the model here: the
/// same shared `PaneFilterBar` container, the same top-on-Mac /
/// bottom-on-touch placement decision.
///
/// Built as ONE container carrying all three rather than three separate
/// relocations — three passes over the same layout is three chances for the
/// container to end up subtly different.
extension LibraryView {
    /// Top on the Mac (controls near the head of the content), bottom on touch
    /// (reachability). The same single platform decision the reader's find bar
    /// makes, taken from the same place so the two panes agree.
    static var miniToolbarPlacement: MiniToolbarPlacement {
        MiniToolbarPlacement.preferredForReader
    }

    /// The bar itself: row attributes, sort, then the narrowing filter row
    /// toggle. The engine-search field is NOT here any more — see below.
    var libraryMiniToolbar: some View {
        libraryMiniToolbar(condensed: false)
    }

    /// `condensed` is the middle rung of the bar's fit ladder (2026-08-31): the
    /// SAME controls with their text labels dropped, tried before anything
    /// collapses into the `…` menu. Giving up a word is cheaper than giving up
    /// a control — which is what "the ellipsis is too greedy" was describing.
    @ViewBuilder
    func libraryMiniToolbar(condensed: Bool) -> some View {
        // The engine-search field moved to the WINDOW toolbar, top right,
        // resident (Daniel's ruling 2026-08-19, #4604 Q10 — supersedes the
        // summoned #4521 field here). Sort, filter, and row attributes stay:
        // they act on this list and only this list.

        Spacer(minLength: 8)

        // Canvas channels (Daniel, 2026-08-23): Arrange + Colour-by act on
        // what the board SHOWS, so they sit in the one bottom bar with sort
        // and filter — only while a canvas mode is up.
        if displayMode.group == .canvas {
            CanvasControlStrip()
        }

        // Dataset facets (Daniel, 2026-08-24: "I want it all in the one at
        // the bottom") — shown only while the dataset has rows.
        if displayMode.group == .dataset, datasetStore.page?.rows.isEmpty == false {
            DatasetFilterCluster(store: datasetStore, documentStore: documentStore)
        }

        // Xcode-console-style metadata popover (#18): which optional
        // attributes list rows display. Sits with sort/filter because it,
        // too, acts on the library list.
        LibraryRowAttributesButton(
            raw: $rowAttributesRaw,
            datasetStore: displayMode.group == .dataset ? datasetStore : nil
        )

        // In dataset mode the level choice lives inside the cluster's Show
        // menu with the types (Daniel, 2026-08-27) — one menu, one question.
        if displayMode.group != .dataset {
            libraryLevelToggle
        }

        librarySortMenu

        libraryFilterToggleButton(iconOnly: condensed)
    }

    /// Spreads ↔ Pages (2026-08-22). Daniel: "I want to be able to show
    /// spreads, or show single pages."
    ///
    /// A diary folder legitimately holds BOTH — openings whose two pages moved
    /// beneath them, and pages that were never split — so the folder's
    /// contents are a genuinely ambiguous question that only the reader can
    /// answer. It sits with sort and filter because it acts on this list and
    /// only this list, the same rule the rest of this bar encodes.
    ///
    /// Always shown, like sort. It is a VIEW MODE, not a contextual action:
    /// the reader's answer to "spreads or pages" is a standing preference, and
    /// a control that appears and disappears as they move between folders is
    /// harder to find than one that is simply always there.
    ///
    /// Deliberately NOT hidden when a folder has no containers. Deciding that
    /// client-side would mean either hard-coding "opening" — the exact thing
    /// the engine-side resolver avoids by reading a prototype attribute — or
    /// guessing from child counts, which mis-fires on a PDF whose pages the
    /// engine will not expand. A wrong guess would hide the control in folders
    /// where it works, or show a dead one where it does not.
    /// Extended to FOUR kinds (Daniel, 2026-08-31): Spreads, Pages, Regions,
    /// Extracted Data — "so the listing can show just pages, just regions".
    /// `LibraryShowKind` owns the mapping; see its doc comment for why two of
    /// the four are an engine tier and two are a client-side narrowing.
    var libraryLevelToggle: some View {
        libraryShowMenu(iconOnly: true)
    }

    /// The Show menu. `iconOnly` is the bar's coat; the overflow `…` menu asks
    /// for the LABELLED coat, because a bare `⇅` chevron row inside a menu says
    /// nothing at all about what it opens (Daniel, 2026-08-31).
    @ViewBuilder
    func libraryShowMenu(iconOnly: Bool) -> some View {
        let current = libraryShowKind
        Menu {
            ForEach(LibraryShowKind.allCases) { kind in
                Button {
                    setLibraryShowKind(kind)
                } label: {
                    Label(kind.title, systemImage: kind.systemImage)
                    if current == kind {
                        Image(systemName: "checkmark")
                    }
                }
                .accessibilityLabel(kind.help)
            }
        } label: {
            if iconOnly {
                Label("Show: \(current.title)", systemImage: current.systemImage)
                    .labelStyle(.iconOnly)
            } else {
                Label("Show: \(current.title)", systemImage: current.systemImage)
            }
        }
        .menuIndicator(.hidden)
        .help(current.help)
        .accessibilityIdentifier("libraryLevelToggle")
    }

    /// What the Show control currently reads, derived rather than stored twice.
    ///
    /// The tier half of the answer lives on the store (the engine resolves it),
    /// so `documentStore.libraryLevel` is the authority for Spreads-vs-the-rest
    /// — the dataset cluster sets that tier too, and a second copy here would be
    /// free to disagree with it. The kind half is the client-side narrowing and
    /// is the only part this view persists.
    var libraryShowKind: LibraryShowKind {
        guard documentStore.libraryLevel == .content else { return .spreads }
        let stored = LibraryShowKind(rawValue: showKindRaw) ?? .pages
        // `.spreads` persisted while the tier says content means something else
        // moved the tier; answer with what the list is actually showing.
        return stored == .spreads ? .pages : stored
    }

    /// Both halves move together: the tier goes to the engine, the narrowing is
    /// persisted, and `recomputeFiltered` re-runs off the persisted value.
    func setLibraryShowKind(_ kind: LibraryShowKind) {
        showKindRaw = kind.rawValue
        Task { await documentStore.setLibraryLevel(kind.level) }
    }

    /// Drives `libraryToolbar` — the SAME sort model the View menu, the table
    /// column headers, and the per-folder `@SceneStorage` persistence already
    /// share. There is deliberately no second sort path (#4282).
    var librarySortMenu: some View {
        librarySortMenu(iconOnly: true)
    }

    /// The same one sort model in two coats. Icon-only in the bar (the label is
    /// the sort FIELD NAME, which would make the pane's minimum width depend on
    /// the user's sort choice); labelled in the overflow menu, where an icon-only
    /// Menu renders as a nameless `⇅` submenu row.
    @ViewBuilder
    func librarySortMenu(iconOnly: Bool) -> some View {
        if iconOnly {
            // The bar's coat keeps the borderless chrome + stable width.
            sortMenuCore(iconOnly: true)
                .menuIndicator(.hidden)
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help(libraryToolbar.sortMenuModel.help)
        } else {
            // Inside a Menu the borderless-button chrome and `.fixedSize()`
            // have nothing to size against — a submenu row is laid out by the
            // menu, so the labelled coat wears neither.
            sortMenuCore(iconOnly: false)
        }
    }

    @ViewBuilder
    private func sortMenuCore(iconOnly: Bool) -> some View {
        let model = libraryToolbar.sortMenuModel
        Menu {
            Section("Sort By") {
                ForEach(model.fields) { field in
                    Button {
                        libraryToolbar.apply(model.selecting(field))
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if model.isSelected(field) {
                            Image(systemName: "checkmark")
                        }
                    }
                    .accessibilityLabel("Sort by \(field.rawValue)")
                }
            }

            Section {
                Button {
                    libraryToolbar.apply(model.settingAscending(true))
                } label: {
                    Label("Ascending", systemImage: "arrow.up")
                    if model.ascending {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    libraryToolbar.apply(model.settingAscending(false))
                } label: {
                    Label("Descending", systemImage: "arrow.down")
                    if !model.ascending {
                        Image(systemName: "checkmark")
                    }
                }
            }
        } label: {
            // ICON ONLY (views audit #6): the label was the SORT FIELD NAME
            // ("Date Modified"…) under .fixedSize(), so the library pane's
            // minimum width varied with the user's sort choice. The icon is
            // stable-width; the field name lives in the menu and the help.
            if iconOnly {
                Label(model.label, systemImage: model.systemImage)
                    .labelStyle(.iconOnly)
            } else {
                Label("Sort By: \(model.label)", systemImage: model.systemImage)
            }
        }
    }

    /// Reveals the inline per-view filter row — the narrowing filter over rows
    /// already loaded, NOT the engine search above.
    ///
    /// The feature flag is untouched on purpose (#4374 finding 4): it defaults
    /// to `false` and `resetToV001()` sets it `false` again, so Filter is
    /// switched OFF rather than broken. Moving the control does not decide
    /// whether to enable it.
    var libraryFilterToggleButton: some View {
        libraryFilterToggleButton(iconOnly: false)
    }

    /// `iconOnly` drops the word "Filter" for the condensed rung of the bar's
    /// fit ladder; the `.help` still names it, so nothing becomes unnameable.
    @ViewBuilder
    func libraryFilterToggleButton(iconOnly: Bool) -> some View {
        let model = LibraryFilterToggleModel(
            isAvailable: featureManager.isLibraryFilterToolbarEnabled,
            isActive: showFilterBar
        )
        if model.isAvailable {
            Toggle(isOn: Binding(
                get: { model.isActive },
                set: { showFilterBar = $0 }
            )) {
                if iconOnly {
                    Label(model.title, systemImage: model.systemImage)
                        .labelStyle(.iconOnly)
                } else {
                    Label(model.title, systemImage: model.systemImage)
                }
            }
            .toggleStyle(.button)
            .help(model.help)
            .accessibilityLabel(model.title)
        }
    }
}
