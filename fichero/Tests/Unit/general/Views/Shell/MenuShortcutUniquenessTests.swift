@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// spec: panes-workspaces §"v2 workspace design" + §"Accessibility is first-class"
/// (`workspaces.one-system`, ⌘⌥1–5 reachability) AND the shortcut-collision bug the CD hit live
/// (2026-09-16): "⌘⌥1 opens the LOUPE instead of applying the Read workspace." A workspace slot and
/// a magnifier verb (or ANY two commands) sharing one chord is a defect — the wrong command fires.
///
/// Menu audit 2026-09-17 REWROTE the source scan below. The prior version only matched the
/// literal `[.command, .option]` array order, so it silently missed:
///   - `[.option, .command]` (FicheroApp.swift's Activity-window ⌥⌘0);
///   - every `toolButton(key:)` mint (PreviewHeadControls.swift's own comment claimed these were
///     "folded in separately below" — no such code existed);
///   - any bare `KeyboardShortcut(` constructor call;
///   - any modifier family OTHER than ⌘⌥ (this is how ⌃⌘F/Enter-Full-Screen, ⌃⌘S/Show-Sidebar and
///     ⌘⌥H/Hide-Others — all real macOS system chords — went unnoticed for as long as they did);
///   - there was no system-reserved denylist at all.
/// It is now ONE table-driven scan of every shortcut mint in `App/` and `Views/Shell/`, grouped by
/// (key, modifier set), checked two ways: (a) no two DIFFERENT commands claim the same chord, and
/// (b) no command claims a macOS system-reserved chord.
struct MenuShortcutUniquenessTests {

    // MARK: - 1. The workspace slots are ⌘⌥1–5, unique, and never the loupe's ⌘⌥L

    /// spec workspaces.one-system + §"the slot→workspace map": ⌘⌥1–5 map to the five built-ins in
    /// declaration order, all distinct, and NONE collides with the loupe's ⌘⌥L
    /// (ImagePreviewMenuCommands.swift). This is the model half of the "⌘⌥1 opened the loupe" bug: it
    /// pins that the workspace slot chords are exactly the digits under ⌘⌥ and share no key with the
    /// magnifier family.
    @Test("⌘⌥ workspace-slot digits map to the built-in workspaces, all distinct, none is the loupe's ⌘⌥L")
    func workspaceSlotsAreUniqueCommandOptionDigits() {
        var seen: Set<String> = []
        for layout in BuiltInWorkspaceLayout.allCases {
            guard let shortcut = WorkspaceCommandsSection.shortcut(for: layout) else {
                Issue.record("\(layout.title) has no ⌘⌥N shortcut — ⌘⌥\(layout.defaultSlot) is unreachable")
                continue
            }
            #expect(
                shortcut.modifiers == [.command, .option],
                "\(layout.title) must bind ⌘⌥, not \(shortcut.modifiers)"
            )
            #expect(
                shortcut.key.character == Character(String(layout.defaultSlot)),
                "\(layout.title) must bind ⌘⌥\(layout.defaultSlot), got \(shortcut.key.character)"
            )
            // The loupe is ⌘⌥L (ImagePreviewMenuCommands.swift). A workspace slot minted as "l" would
            // be the exact collision the CD saw; assert the slot key is never the loupe's.
            #expect(
                shortcut.key.character != "l",
                "\(layout.title) minted ⌘⌥L — the loupe's chord (the reported ⌘⌥1→loupe mis-fire)"
            )
            let token = chordToken(shortcut)
            #expect(!seen.contains(token), "\(layout.title) reuses the ⌘⌥ chord \(token)")
            seen.insert(token)
        }
        #expect(
            seen.count == BuiltInWorkspaceLayout.allCases.count,
            "every built-in workspace must have its own distinct ⌘⌥ chord"
        )
    }

    private func chordToken(_ shortcut: KeyboardShortcut) -> String {
        "\(shortcut.key.character)-\(shortcut.modifiers.rawValue)"
    }

    // MARK: - 2. One table-driven scan: no collisions, nothing system-reserved

    /// A single shortcut mint: which file + line minted it, the normalized key, and the canonical
    /// (alphabetically-sorted) modifier-set token, e.g. `"command+option"`.
    private struct Mint: Hashable {
        let file: String
        let line: Int
        let key: String
        let modifiers: String
    }

    /// Verbs that DELIBERATELY share one chord because their commands are gated by mutually
    /// exclusive `@FocusedValue`s — never both enabled at once, so there is no actual ambiguity
    /// about which one fires. Each entry is a `key-modifiers` chord token; document the reason at
    /// BOTH call sites, not just here.
    ///   - `"9-command"` — "Zoom to Fit": `CanvasViewSection.hasFocusedCanvas`
    ///     (CanvasMenuCommands.swift) vs `ImagePreviewMenuCommands.hasActiveImagePreview` — a pane is
    ///     never both a canvas and an image/reader preview at once (menu audit 2026-09-17). Moved off
    ///     ⌘= (review 2026-09-17, #4693): a mask without `.shift` matches on
    ///     `charactersIgnoringModifiers`, which un-shifts back to "=" even when Shift IS held, so a
    ///     bare ⌘= item also intercepts ⌘⇧= (⌘+) ahead of "Zoom In"'s own key equivalent. ⌘9 shares no
    ///     physical key with the +/- zoom chords, so it can't repeat that.
    ///   - `"f-command+option"` — "Find in Page" (`ShowFindBarButton`,
    ///     ViewMenuPaneSections.swift): ONE command declared twice inside an
    ///     `#if canImport(AppKit) / #else` platform branch, not two commands.
    ///     Surfaced by the per-site (not per-file) grouping fix below (#4693)
    ///     — the scanner reads raw lines and has no `#if`/`#else` awareness, so
    ///     it cannot tell "same command, two platform bodies" from a genuine
    ///     duplicate; only one branch ever compiles for a given platform.
    private static let allowedSharedChords: Set<String> = [
        "9-command",
        "f-command+option",
    ]

    /// macOS chords the app must never claim as its own `NSMenuItem` key equivalent — either because
    /// AppKit/the system already owns them UNCONDITIONALLY (a second claim races the system's, the
    /// exact ⌘⌥T/⌘⌥H/⌃⌘F bugs the menu audit found), or because the app has ruled the chord belongs
    /// to a command it hasn't wired yet (⌃⌘S — see ViewMenuLayoutSections.swift's note: freed for a
    /// future Show/Hide Sidebar command; nothing may squat on it meanwhile). Each entry below is kept
    /// because the chord is reserved REGARDLESS of what has focus:
    ///   - `h-command+option` — "Hide Others" (fixed AppKit application-menu item).
    ///   - `t-command+option` — "Show/Hide Toolbar" (fixed AppKit window-menu item).
    ///   - `d-command+option` — "Turn Dock Hiding On/Off" (fixed system chord).
    ///   - `f-command+control` — "Enter Full Screen" (fixed AppKit window-menu item).
    ///   - `s-command+control` — reserved for a not-yet-wired Show/Hide Sidebar command (see above).
    ///   - `h-command` — "Hide Fichero" (fixed AppKit application-menu item).
    ///   - `q-command` — "Quit Fichero" (fixed AppKit application-menu item).
    ///   - `,-command` — "Preferences…" (fixed AppKit application-menu item).
    ///
    /// Menu audit 2026-09-17 review (#4693): the Format-menu chords (⌘T/⌘I/⌘B/⌘U/⌘+/⌘-) used to live
    /// in this table too, but they are NOT system-reserved — they are SwiftUI's built-in
    /// `TextFormattingCommands()` (wrapped by `FormatMenuCommands`, ViewMenuPaneSections.swift), which
    /// only registers a live key equivalent while a focused text view accepts it. Denylisting them
    /// unconditionally produced false positives against always-enabled commands that happen to reuse
    /// the same physical key while NO text editor has focus — File's "New Window" (⌘T) and Image
    /// Preview's "Zoom In"/"Zoom Out" (⌘+/⌘-) and the sidebar's "Link Files…" (⌘I) all tripped this
    /// test though none of them can ever fire at the same moment as the Format item they were flagged
    /// against. If a REAL collision between a Format chord and a non-text command turns up, it belongs
    /// in `allowedSharedChords` (documented per-site, like the Zoom-to-Fit entry below) or needs its
    /// own focus-gating fix — not a blanket reservation here.
    private static let systemReservedChords: [String: String] = [
        "h-command+option": "Hide Others",
        "t-command+option": "Show/Hide Toolbar",
        "d-command+option": "Turn Dock Hiding On/Off",
        "f-command+control": "Enter Full Screen",
        "s-command+control": "Show/Hide Sidebar (reserved, unwired — see ViewMenuLayoutSections.swift)",
        "h-command": "Hide Fichero",
        "q-command": "Quit Fichero",
        ",-command": "Preferences…",
    ]

    @Test("no two different commands claim the same shortcut, across the whole app")
    func noTwoCommandsShareAChord() throws {
        let mints = try allMints()
        #expect(!mints.isEmpty, "found no shortcut mints — the scan root or patterns are wrong")

        // Grouped by CHORD alone (not by distinct file first) — two mints of the
        // same chord in the SAME file are just as real a double-bind as two
        // mints across different files (menu audit 2026-09-17 review, #4693):
        // the toolbar's ⌘' Back button and the Go menu's ⌘' Back button are two
        // different files, but two `.keyboardShortcut` calls for the same
        // command in one file would have been invisible to a files.count-based
        // check. Every SITE counts, so `sites.count > 1` catches both shapes.
        var sitesByChord: [String: [Mint]] = [:]
        for mint in mints {
            let chord = "\(mint.key)-\(mint.modifiers)"
            sitesByChord[chord, default: []].append(mint)
        }

        for (chord, sites) in sitesByChord where sites.count > 1 && !Self.allowedSharedChords.contains(chord) {
            let siteList = sites
                .map { "\($0.file):\($0.line)" }
                .sorted()
                .joined(separator: ", ")
            let detail: String = "Shortcut \(chord) is bound by \(sites.count) different mints — \(siteList). "
                + "Two commands sharing one chord means the wrong one can fire (the ⌘⌥1→loupe bug class)."
            Issue.record("\(detail)")
        }
        let collisions = sitesByChord.keys
            .filter { (sitesByChord[$0]?.count ?? 0) > 1 && !Self.allowedSharedChords.contains($0) }
            .sorted()
        #expect(collisions.isEmpty, "colliding shortcuts: \(collisions)")
    }

    @Test("no command claims a macOS system-reserved chord")
    func noCommandClaimsASystemReservedChord() throws {
        let mints = try allMints()
        for mint in mints {
            let chord = "\(mint.key)-\(mint.modifiers)"
            if let reservedFor = Self.systemReservedChords[chord] {
                let detail: String = "\(mint.file):\(mint.line) claims \(chord), which macOS/the app "
                    + "reserves for \"\(reservedFor)\" — pick a different chord."
                Issue.record("\(detail)")
            }
        }
    }

    // MARK: - Source scan

    /// Every shortcut mint under `App/` and `Views/Shell/`:
    ///   - `.keyboardShortcut("x", modifiers: [...])` (any modifier order/count);
    ///   - `.keyboardShortcut("x", modifiers: .command)` (bare single modifier);
    ///   - `.keyboardShortcut(.delete, modifiers: [...])` (named `KeyEquivalent` constants);
    ///   - `KeyboardShortcut("x", modifiers: [...])` (the positional constructor);
    ///   - the app's two `key:`/`shortcut:` indirections that feed a HARDCODED modifier set into a
    ///     reusable button: `PreviewHeadControls.toolButton(key:)` → always ⌘⌥, and
    ///     `PreviewModeButton`/`SidebarModeButton(shortcut:)` → always ⌃⌘. These are matched by name
    ///     rather than a general parameter-flow analysis — the app has exactly these two indirections
    ///     today; a third should extend this list, not motivate a bigger analyzer.
    /// The workspace digit slots (⌘⌥1–5, minted from `BuiltInWorkspaceLayout` DATA, not a source
    /// literal) are asserted separately in test 1 above, against the loupe only — they are Assistant/
    /// data-driven, not scannable text, and test 1 already proves them internally unique.
    private func allMints() throws -> [Mint] {
        let root = try AppSource.root().standardizedFileURL
        guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil) else {
            return []
        }

        let bracketed = try NSRegularExpression(
            pattern: #"\.keyboardShortcut\(\s*"(.)"\s*,\s*modifiers:\s*\[([^\]]+)\]\s*\)"#
        )
        let bareModifier = try NSRegularExpression(
            pattern: #"\.keyboardShortcut\(\s*"(.)"\s*,\s*modifiers:\s*(\.\w+)\s*\)"#
        )
        let namedKeyEquivalent = try NSRegularExpression(
            pattern: #"\.keyboardShortcut\(\s*\.(delete|escape|return|tab|space)\s*,\s*modifiers:\s*\[([^\]]+)\]\s*\)"#
        )
        let constructor = try NSRegularExpression(
            pattern: #"KeyboardShortcut\(\s*"(.)"\s*,\s*modifiers:\s*\[([^\]]+)\]\s*\)"#
        )
        let toolButtonKey = try NSRegularExpression(pattern: #"key:\s*"(.)""#)
        let previewOrSidebarShortcut = try NSRegularExpression(pattern: #"shortcut:\s*"(.)""#)

        var mints: [Mint] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            guard relative.hasPrefix("App/") || relative.hasPrefix("Views/Shell/") else { continue }
            let source = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            let lines = source.components(separatedBy: .newlines)
            for (index, rawLine) in lines.enumerated() {
                if rawLine.trimmingCharacters(in: .whitespaces).hasPrefix("//") { continue }
                let range = NSRange(rawLine.startIndex..<rawLine.endIndex, in: rawLine)
                let line = index + 1

                for match in bracketed.matches(in: rawLine, range: range) {
                    Self.record(&mints, rawLine, match, keyGroup: 1, modifiersGroup: 2, file: relative, line: line)
                }
                for match in bareModifier.matches(in: rawLine, range: range) {
                    Self.record(&mints, rawLine, match, keyGroup: 1, modifiersGroup: 2, file: relative, line: line)
                }
                for match in namedKeyEquivalent.matches(in: rawLine, range: range) {
                    Self.record(&mints, rawLine, match, keyGroup: 1, modifiersGroup: 2, file: relative, line: line)
                }
                for match in constructor.matches(in: rawLine, range: range) {
                    Self.record(&mints, rawLine, match, keyGroup: 1, modifiersGroup: 2, file: relative, line: line)
                }

                // The two known key:/shortcut: indirections — matched by declaring file, since both
                // wrap their key parameter in a HARDCODED modifier set the regex above can't see.
                if relative == "Views/Shell/PaneHead/PreviewHeadControls.swift",
                   let match = toolButtonKey.firstMatch(in: rawLine, range: range),
                   let keyRange = Range(match.range(at: 1), in: rawLine) {
                    mints.append(Mint(
                        file: relative, line: line,
                        key: String(rawLine[keyRange]).lowercased(),
                        modifiers: Self.canonicalModifiers(".command, .option")
                    ))
                }
                if relative == "App/Menus/ViewMenuLayoutSections.swift" || relative == "App/Menus/ViewMenuCommands.swift",
                   let match = previewOrSidebarShortcut.firstMatch(in: rawLine, range: range),
                   let keyRange = Range(match.range(at: 1), in: rawLine) {
                    mints.append(Mint(
                        file: relative, line: line,
                        key: String(rawLine[keyRange]).lowercased(),
                        modifiers: Self.canonicalModifiers(".command, .control")
                    ))
                }
            }
        }
        return mints
    }

    private static func record(
        _ mints: inout [Mint],
        _ rawLine: String,
        _ match: NSTextCheckingResult,
        keyGroup: Int,
        modifiersGroup: Int,
        file: String,
        line: Int
    ) {
        guard let keyRange = Range(match.range(at: keyGroup), in: rawLine) else { return }
        let modifierText: String
        if match.numberOfRanges > modifiersGroup, let modRange = Range(match.range(at: modifiersGroup), in: rawLine) {
            modifierText = String(rawLine[modRange])
        } else {
            modifierText = ".command"
        }
        mints.append(Mint(
            file: file, line: line,
            key: String(rawLine[keyRange]).lowercased(),
            modifiers: canonicalModifiers(modifierText)
        ))
    }

    /// Canonical, order-independent modifier token — catches `[.option, .command]` exactly like
    /// `[.command, .option]`, which the prior test's fixed-order regex could not.
    private static func canonicalModifiers(_ raw: String) -> String {
        var tokens: Set<String> = []
        if raw.contains("command") { tokens.insert("command") }
        if raw.contains("option") { tokens.insert("option") }
        if raw.contains("control") { tokens.insert("control") }
        if raw.contains("shift") { tokens.insert("shift") }
        if tokens.isEmpty { tokens.insert("command") }
        return tokens.sorted().joined(separator: "+")
    }
}
