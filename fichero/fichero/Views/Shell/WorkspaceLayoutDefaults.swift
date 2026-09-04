import Foundation

// MARK: - The layout a new window (or a relaunch) starts in (Daniel, 2026-09-04)

/// "Make sure workspace is saved when we quit — panes reset each time."
///
/// They did, and the reason is structural rather than a missing save.
/// `showDocumentGrid` / `showDocumentCanvas` / `showReadingPane` /
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
/// Plain `UserDefaults`, deliberately, rather than `@AppStorage` properties on
/// `ContentView`: that type is size-capped (`ViewValueSizeTests`, stalls.log
/// 2026-08-24) because every main-thread graph update copies it, and five more
/// property wrappers would have blown the ceiling to fix a persistence bug.
enum WorkspaceLayoutDefaults {

    /// One remembered value. Raw strings rather than an enum-with-rawValue so
    /// the key a window reads is greppable from the key a toggle writes.
    enum Key: String, CaseIterable {
        case grid = "workspace.showDocumentGrid"
        case canvas = "workspace.showDocumentCanvas"
        case reading = "workspace.showReadingPane"
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
    /// The three content panes and the chat pane each have exactly one
    /// deliberate mutation path (`setPaneVisible`, `setChatPaneVisible`), which
    /// is what makes them safe to remember. `sidebarMode` is out for the same
    /// reason, with twenty writers.
    static var showDocumentGrid: Bool { pane(.grid, default: true) }
    static var showDocumentCanvas: Bool { pane(.canvas, default: true) }
    static var showReadingPane: Bool { pane(.reading, default: true) }
    static var showChatPane: Bool { pane(.chat, default: true) }

    /// Remember what the user left, so the next window opens there.
    ///
    /// Takes the whole visibility value rather than one pane at a time: it is
    /// written from `setPaneVisible`, which has already applied the
    /// "≥1 pane visible" invariant (#1696), so what is stored is a layout that
    /// invariant would accept — never a combination a window could not open in.
    static func remember(_ visibility: PaneVisibility, chat: Bool, in store: UserDefaults = .standard) {
        setPane(.grid, visibility.grid, in: store)
        setPane(.canvas, visibility.canvas, in: store)
        setPane(.reading, visibility.reading, in: store)
        setPane(.chat, chat, in: store)
    }

    /// The remembered layout, as the invariant type — so a caller reads one
    /// value rather than reassembling three booleans.
    static func rememberedVisibility(in store: UserDefaults = .standard) -> PaneVisibility {
        let remembered = PaneVisibility(
            grid: pane(.grid, default: true, in: store),
            canvas: pane(.canvas, default: true, in: store),
            reading: pane(.reading, default: true, in: store)
        )
        // A store written before the #1696 invariant existed — or edited by
        // hand — could name an all-hidden layout, which no window may open in.
        // Refuse it here rather than opening an empty content area.
        return remembered.isAnyVisible ? remembered : PaneVisibility(grid: true, canvas: true, reading: true)
    }
}
