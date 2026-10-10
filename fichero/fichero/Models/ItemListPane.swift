import Foundation

/// The middle pane's name: **Item List** (ruled 2026-10-10, DEVONthink's and Zotero's term; it
/// was "Library", which is now only ever a project). The window reads Project · Item List ·
/// Source View · Inspector (Source View is a later pass; Preview keeps its name until then).
/// Every place that names the pane reads `name` (View › Show/Hide, the pane head, Settings, the
/// mode label, the toolbar help, accessibility), so a rename is one line
/// (`library.item-list.one-name` in `docs/contributor_manual/specs/ui/sidebar-crud.md`). Two
/// places must stay literal because App Intents reads them at build time (`UIPane`'s display
/// representation and the intent descriptions); `ItemListPaneNameTests` pins them to this.
nonisolated enum ItemListPane {
    /// The pane's name. Change only this line (and the two App Intents literals the test names).
    static let name = "Item List"

    static var showLabel: String { "Show \(name)" }
    static var hideLabel: String { "Hide \(name)" }
}
