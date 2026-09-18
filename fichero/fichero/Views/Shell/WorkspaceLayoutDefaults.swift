import Foundation

// MARK: - The layout a new window (or a relaunch) starts in (Daniel, 2026-09-04)

/// "Make sure workspace is saved when we quit — panes reset each time."
///
/// They did, and the reason is structural rather than a missing save.
/// `showChatPane` / `currentLayoutMode` are `@SceneStorage`: per-WINDOW state
/// that SwiftUI persists through macOS scene restoration. Scene state does not
/// survive a quit unless the system restores windows, so on the next launch
/// every one of them fell back to its literal default — a fresh window with
/// all panes on, whatever the user left.
///
/// The pane WIDTHS beside them always survived, because they are `@AppStorage`
/// (`sidebarWidth`, `contentWidth`, `inspectorWidth`…) — plain UserDefaults,
/// which is not restoration-dependent. That asymmetry is the whole bug, and
/// the codebase already met it once: #943 was "set List, switch items, reverts
/// to Icon", fixed by mirroring the view display mode into an `@AppStorage`
/// default described in its own comment as surviving "window close, fresh
/// launches". That fix was never applied to the panes.
///
/// This is that same mirror, for the layout. The `@SceneStorage` values stay
/// exactly as they are — per-window, so two windows still diverge — and these
/// defaults only decide what a window STARTS as.
///
/// The three CONTENT-pane Bools this originally mirrored (`showDocumentGrid` /
/// `showDocumentCanvas` / `showReadingPane`) are GONE (#4687): `paneVisibility`
/// is now a pure derivation of `activePaneList.kinds`, and the applied
/// `PaneList` itself is what gets remembered (`rememberedPaneList`/
/// `rememberPaneList`, below) — there is no separate pane-visibility shape left
/// to seed or write back. Only `chat` (not part of `PaneList`) still needs this
/// Bool mirror.
///
/// Plain `UserDefaults`, deliberately, rather than `@AppStorage` properties on
/// `ContentView`: that type is size-capped (`ViewValueSizeTests`, stalls.log
/// 2026-08-24) because every main-thread graph update copies it, and five more
/// property wrappers would have blown the ceiling to fix a persistence bug.
enum WorkspaceLayoutDefaults {

    /// One remembered value. Raw strings rather than an enum-with-rawValue so
    /// the key a window reads is greppable from the key a toggle writes.
    enum Key: String, CaseIterable {
        case chat = "workspace.showChatPane"
        case layoutMode = "workspace.currentLayoutMode"
    }

    /// A remembered pane state, or `fallback` when the user has never chosen.
    ///
    /// `object(forKey:)`, not `bool(forKey:)`: the latter answers `false` for a
    /// key that was never written, which would open every first-run window with
    /// its panes hidden — the defaults here are `true`, and "absent" must mean
    /// "no preference", not "off".
    static func pane(_ key: Key, default fallback: Bool, in store: UserDefaults = .standard) -> Bool {
        store.object(forKey: key.rawValue) as? Bool ?? fallback
    }

    static func setPane(_ key: Key, _ value: Bool, in store: UserDefaults = .standard) {
        store.set(value, forKey: key.rawValue)
    }

    static func layoutModeRaw(default fallback: String, in store: UserDefaults = .standard) -> String {
        store.string(forKey: Key.layoutMode.rawValue) ?? fallback
    }

    static func setLayoutModeRaw(_ value: String, in store: UserDefaults = .standard) {
        store.set(value, forKey: Key.layoutMode.rawValue)
    }

    // MARK: - What a window starts as

    /// Deliberately NOT mirrored: the sidebar and inspector visibility.
    ///
    /// Both have a dozen PROGRAMMATIC writers — a claim-source reveal, an
    /// AppleScript `show panel`, a search summoning its chrome — and mirroring
    /// those would record a transient reveal as the user's chosen workspace.
    /// Chat has exactly one deliberate mutation path (`setChatPaneVisible`),
    /// which is what makes it safe to remember. `sidebarMode` is out for the
    /// same reason, with twenty writers. The three content panes used to be
    /// remembered here too; `rememberedPaneList`/`rememberPaneList` below now
    /// carry that (#4687 — `paneVisibility` has no storage of its own left to
    /// seed).
    static var showChatPane: Bool { pane(.chat, default: true) }

    /// Remember the chat pane's visibility, so the next window opens there
    /// (Daniel, 2026-09-04: "panes reset each time"). The three content panes
    /// no longer need a call here — they ride `activePaneList` itself, via
    /// `rememberPaneList` in the same funnel this is called from.
    static func remember(chat: Bool, in store: UserDefaults = .standard) {
        setPane(.chat, chat, in: store)
    }

    // MARK: - The last-applied PaneList (#4686)

    /// A separate raw key, NOT a `Key` case: every `Key` above is a Bool remembered through
    /// `pane`/`setPane`, and `testOnlyTheDeliberatelyChosenSurfacesAreRemembered` inventories
    /// exactly that Bool set. The applied composition is JSON `Data`, a different shape, so it
    /// gets its own key rather than forcing that inventory to carry a non-Bool entry.
    private static let appliedPaneListKey = "workspace.appliedPaneList"

    /// The last `PaneList` a window applied (⌘⌥N, a saved-workspace apply, a split/close/kind
    /// change), or `nil` when nothing has ever been remembered — a fresh install, or a store
    /// written before this existed. The caller decides the fallback (the Read default), the same
    /// "absent is not a value" contract `pane(_:default:)` uses for the Bools.
    static func rememberedPaneList(in store: UserDefaults = .standard) -> PaneList? {
        guard let data = store.data(forKey: appliedPaneListKey) else { return nil }
        return try? JSONDecoder().decode(PaneList.self, from: data)
    }

    /// Remember `list` as the one to restore on the next launch (#4686 — "make sure workspace is
    /// saved when we quit" was ALSO true of the applied composition, not only pane visibility).
    static func rememberPaneList(_ list: PaneList, in store: UserDefaults = .standard) {
        guard let data = try? JSONEncoder().encode(list) else { return }
        store.set(data, forKey: appliedPaneListKey)
    }
}
