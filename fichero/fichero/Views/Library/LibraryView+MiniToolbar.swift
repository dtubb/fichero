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
        // the bottom"). ONE EXTRA, never a substitute (Daniel, 2026-09-01:
        // "data/dataset mode shows a different bar"): the cluster used to
        // carry its own Show menu with the reading level in it AND the shared
        // Show control was suppressed below, so switching to Data swapped one
        // control for a differently-named one in the same slot — which is what
        // made the bar read as a different bar. The cluster now adds only what
        // is genuinely extra to this mode, the row types and the date facet,
        // and the shared Show / Sort / Filter / Metadata controls stay exactly
        // where they are in every other mode.
        //
        // No longer gated on the dataset having rows, either: a control that
        // appears once data lands is a bar that changes shape under the user.
        if displayMode.group == .dataset {
            DatasetFilterCluster(store: datasetStore, documentStore: documentStore)
        }

        // The document-list controls — row attributes, reading level, sort,
        // filter — act on the DOCUMENT list, so they show only while browsing
        // documents. In Claims / Entities mode the table owns its own column
        // sort and those controls would be dead affordances over a different kind
        // of row (Daniel: no-op controls confuse a demo).
        // #4884: gates on what's ACTUALLY rendering, not the raw local
        // fallback — `libraryContentKind` alone stopped being a reliable
        // "documents vs. KG table" signal once it could be nil (never
        // touched) or overridden per-pane via the chip/workspace config.
        if effectiveContentKind == .documents {
            // Xcode-console-style metadata popover (#18): which optional
            // attributes list rows display. Sits with sort/filter because it,
            // too, acts on the library list.
            LibraryRowAttributesButton(
                raw: $rowAttributesRaw,
                contentLines: $rowContentLinesRaw,
                datasetStore: displayMode.group == .dataset ? datasetStore : nil
            )

            // The Show control is in EVERY mode (2026-09-01). It used to be hidden
            // in Data mode on the theory that the cluster's own Show menu carried
            // the level — see `DatasetFilterCluster` for why that swap is gone.
            // The reading level is a library-wide question (`documentStore
            // .libraryLevel`), so the library-wide control is the one that asks it.
            // Metadata · Sort · Filter (`panes.chrome.one-filter-pattern`, owner 2026-11-13): the Show kinds (the old
            // 🗎 control) and the entity filter are in the Filter's menu; the filter is one inline field, no second
            // row. Sort is left out on the Map, where position is the place.
            if Self.barShowsSort(displayMode) { librarySortMenu }

            // The control still asks the feature flag rather than assuming it.
            if featureManager.isLibraryFilterToolbarEnabled {
                PaneFilterField(text: $searchText, accessibilityID: "libraryFilterField", focus: $filterFieldFocused) {
                    libraryFilterMenuContent
                }
                .frame(minWidth: 90, maxWidth: 200)
            }
        } else {
            // Claims and Entities: the same field over their own list (#4856's filter, one control).
            PaneFilterField(
                text: $kgContentFilterText,
                prompt: effectiveContentKind == .claims ? "Filter claims" : "Filter entities",
                accessibilityID: "kgContentFilterField"
            ) {
                Button("All types") { kgContentFilterType = nil }
                Divider()
                ForEach(kgContentAvailableTypes, id: \.self) { type in
                    Button(type.capitalized) { kgContentFilterType = type }
                }
            }
            .frame(minWidth: 90, maxWidth: 200)
        }
    }

    /// Whether the Items bar shows Sort in a view: everywhere but the Map (`panes.chrome.one-filter-pattern`).
    nonisolated static func barShowsSort(_ mode: ViewDisplayMode) -> Bool { mode != .geoMap }

    /// The Items Filter's menu: what the list shows (the Show kinds), and in List the entity filter.
    @ViewBuilder
    var libraryFilterMenuContent: some View {
        let current = libraryShowKind
        Section("Show") {
            ForEach(LibraryShowKind.allCases) { kind in
                Button {
                    setLibraryShowKind(kind)
                } label: {
                    Label(kind.title, systemImage: kind.systemImage)
                    if current == kind { Image(systemName: "checkmark") }
                }
                .accessibilityLabel(kind.help)
            }
        }
        if displayMode == .list {
            entityFilterMenu
        }
    }

    /// Spreads ↔ Pages ↔ Regions ↔ Extracted Data (2026-08-22, 2026-08-31): the Show kinds are the first section of the
    /// Filter field's menu (`libraryFilterMenuContent`, owner 2026-11-13), in every mode, never swapped out by one.

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
                        arrangeCanvasBySortIfShown()
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
                    arrangeCanvasBySortIfShown()
                } label: {
                    Label("Ascending", systemImage: "arrow.up")
                    if model.ascending {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    libraryToolbar.apply(model.settingAscending(false))
                    arrangeCanvasBySortIfShown()
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

    /// Switching kind clears the selection: a document-id selection must not leak
    /// into the claims/entities list, where the ids mean something else. No head
    /// control drives it any more (`panes.chrome.items-head-has-no-kind-menu`,
    /// owner 2026-11-13); unused until a Filter option takes it.
    ///
    /// #4884: the chip now DISPLAYS the effective kind (so a pane that's
    /// following the window shows what it's actually following, not a stale
    /// "Documents" while an entities table renders under it), and WRITES an
    /// EXPLICIT choice — through `\.paneContentKindSwitcher` when this pane
    /// has a slot (persisted into the workspace's `PaneConfig`), else the
    /// local `libraryContentKind` fallback (the compact-iPhone leaf, which
    /// has none). Choosing "Documents" is exactly as explicit/sticky as
    /// choosing Claims or Entities — never special-cased back to "follow the
    /// window" — the maintainer's "Library panes are not linked" ruling.
    var contentKindBinding: Binding<LibraryContentKind> {
        Binding(
            get: { effectiveContentKind },
            set: { newKind in
                guard newKind != effectiveContentKind else { return }
                selection = []
                // #4856: the shared footer's filter slot is reused across
                // whichever KG content kind is active — a claim-type filter
                // must not silently narrow the entities table you just
                // switched to.
                kgContentFilterText = ""
                kgContentFilterType = nil
                kgContentAvailableTypes = []
                if let paneContentKindSwitcher {
                    paneContentKindSwitcher.switchContentKind(newKind)
                } else {
                    libraryContentKind = newKind
                }
            }
        )
    }
}
