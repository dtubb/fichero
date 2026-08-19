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
    @ViewBuilder
    var libraryMiniToolbar: some View {
        // The engine-search field moved to the WINDOW toolbar, top right,
        // resident (Daniel's ruling 2026-08-19, #4604 Q10 — supersedes the
        // summoned #4521 field here). Sort, filter, and row attributes stay:
        // they act on this list and only this list.

        Spacer(minLength: 8)

        // Xcode-console-style metadata popover (#18): which optional
        // attributes list rows display. Sits with sort/filter because it,
        // too, acts on the library list.
        LibraryRowAttributesButton(raw: $rowAttributesRaw)

        librarySortMenu

        libraryFilterToggleButton
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
