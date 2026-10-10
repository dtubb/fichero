import Foundation

/// The middle pane's name: **Items** (ruled 2026-10-10; it was "Library", which is now only ever
/// a project). The window's panes are one word each: Projects (the sidebar) · Items · Source (the
/// preview/editor pane, still "Preview" until its own pass) · Inspector · Reader · Segments.
/// "Item List", "Browser", "Source View" and "Source Preview" were considered and rejected.
/// Every place that names the pane reads `name` (View › Show/Hide, the pane head, Settings, the
/// mode label, the toolbar help, accessibility), so a rename is one line
/// (`sidebar.panes.one-word-names` in `docs/contributor_manual/specs/ui/sidebar-crud.md`). Two
/// places stay literal because App Intents reads them at build time (`UIPane`'s display
/// representation and the intent descriptions); `ProjectNamingTests` pins them to this.
nonisolated enum ItemsPane {
    /// The pane's name. Change only this line (and the two App Intents literals the test names).
    static let name = "Items"

    static var showLabel: String { "Show \(name)" }
    static var hideLabel: String { "Hide \(name)" }
}
