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

    /// The bar itself. Order is scope-widest-first: what you are looking for,
    /// then how it is ordered, then whether the narrowing filter row is open.
    ///
    /// The search field is SUMMONED, not resident (#4521): it renders only
    /// while `searchFieldVisible` is on — the toolbar's search toggle (or a
    /// programmatic search) reveals it. Sort and filter stay resident; they
    /// are not search chrome.
    @ViewBuilder
    var libraryMiniToolbar: some View {
        if searchFieldVisible.wrappedValue {
            librarySearchField
        }

        Spacer(minLength: 8)

        librarySortMenu

        libraryFilterToggleButton
    }

    /// The engine-backed search, now scoped to the pane it fills with results.
    ///
    /// Deliberately a plain field rather than `.searchable`: that API attaches
    /// to a navigation container, which is precisely how it ended up spanning
    /// three panes. The Ask/Keyword choice it used to render as a window-wide
    /// scope bar is a menu here, beside the field it modifies.
    @ViewBuilder
    private var librarySearchField: some View {
        HStack(spacing: 6) {
            Image(systemName: ToolbarSymbols.findField)
                .foregroundStyle(.secondary)
                .font(.body)
                .imageScale(.small)

            TextField("Search", text: searchFieldText)
                .textFieldStyle(.plain)
                .font(.callout)
                // While focused, the row keyboard grammar stands down —
                // ancestor `.onKeyPress` handlers otherwise swallow every
                // character before the field sees it (2026-08-11).
                .focused($searchFieldFocused)
                // Summoned means ready to type: the toolbar toggle reveals
                // this field, so it takes focus on arrival.
                .onAppear { searchFieldFocused = true }
                .onSubmit { onToolbarSearchSubmit(searchFieldText.wrappedValue) }

            if !searchFieldText.wrappedValue.isEmpty {
                Button {
                    searchFieldText.wrappedValue = ""
                } label: {
                    Image(systemName: ToolbarSymbols.clearField)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
                .help("Clear search")
            }

            searchModeMenu
        }
        // Bounded BOTH ways (views audit #6): the bare minWidth was an
        // unshrinkable 140pt floor that propagated up and helped set the
        // library pane's 300-340pt minimum ("the mini toolbars are screwing
        // up the width of the centre views"). The field still grows into
        // available space, but no longer dictates the pane's floor.
        .frame(minWidth: 80, maxWidth: 280)
    }

    /// Ask vs Keyword. Was `.searchScopes`, which is what actually drew the
    /// full-width bar under the toolbar (#4407).
    @ViewBuilder
    private var searchModeMenu: some View {
        Menu {
            Button {
                searchFieldMode.wrappedValue = .ask
            } label: {
                Label("Ask", systemImage: "sparkles")
                if searchFieldMode.wrappedValue == .ask {
                    Image(systemName: "checkmark")
                }
            }
            Button {
                searchFieldMode.wrappedValue = .keyword
            } label: {
                Text("Keyword")
                if searchFieldMode.wrappedValue == .keyword {
                    Image(systemName: "checkmark")
                }
            }
        } label: {
            Label(
                searchFieldMode.wrappedValue == .ask ? "Ask" : "Keyword",
                systemImage: searchFieldMode.wrappedValue == .ask ? "sparkles" : "textformat"
            )
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("Search your words as typed, or ask a question in plain language")
    }

    /// Drives `libraryToolbar` — the SAME sort model the View menu, the table
    /// column headers, and the per-folder `@SceneStorage` persistence already
    /// share. There is deliberately no second sort path (#4282).
    @ViewBuilder
    var librarySortMenu: some View {
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
            Label(model.label, systemImage: model.systemImage)
                .labelStyle(.iconOnly)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help(model.help)
    }

    /// Reveals the inline per-view filter row — the narrowing filter over rows
    /// already loaded, NOT the engine search above.
    ///
    /// The feature flag is untouched on purpose (#4374 finding 4): it defaults
    /// to `false` and `resetToV001()` sets it `false` again, so Filter is
    /// switched OFF rather than broken. Moving the control does not decide
    /// whether to enable it.
    @ViewBuilder
    var libraryFilterToggleButton: some View {
        let model = LibraryFilterToggleModel(
            isAvailable: featureManager.isLibraryFilterToolbarEnabled,
            isActive: showFilterBar
        )
        if model.isAvailable {
            Toggle(isOn: Binding(
                get: { model.isActive },
                set: { showFilterBar = $0 }
            )) {
                Label(model.title, systemImage: model.systemImage)
            }
            .toggleStyle(.button)
            .help(model.help)
        }
    }
}
