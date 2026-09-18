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
    ///   - `"=-command"` — "Zoom to Fit": `CanvasViewSection.hasFocusedCanvas`
    ///     (CanvasMenuCommands.swift) vs `ImagePreviewMenuCommands.hasActiveImagePreview` — a pane is
    ///     never both a canvas and an image/reader preview at once (menu audit 2026-09-17).
    private static let allowedSharedChords: Set<String> = [
        "=-command",
    ]

    /// macOS chords the app must never claim as its own `NSMenuItem` key equivalent — either because
    /// AppKit/the system already owns them (a second claim races the system's, the exact ⌘⌥T/⌘⌥H/⌃⌘F
    /// bugs the menu audit found), or because the app has ruled the chord belongs to a command it
    /// hasn't wired yet (⌃⌘S — see ViewMenuLayoutSections.swift's note: freed for a future Show/Hide
    /// Sidebar command; nothing may squat on it meanwhile).
    private static let systemReservedChords: [String: String] = [
        "h-command+option": "Hide Others",
        "t-command+option": "Show/Hide Toolbar",
        "d-command+option": "Turn Dock Hiding On/Off",
        "f-command+control": "Enter Full Screen",
        "s-command+control": "Show/Hide Sidebar (reserved, unwired — see ViewMenuLayoutSections.swift)",
        "h-command": "Hide Fichero",
        "q-command": "Quit Fichero",
        ",-command": "Preferences…",
        // Standard Format-menu chords (TextFormattingCommands is live — FormatMenuCommands wraps it).
        "t-command": "Format ▸ Show Fonts",
        "i-command": "Format ▸ Italic",
        "b-command": "Format ▸ Bold",
        "u-command": "Format ▸ Underline",
        "+-command": "Format ▸ Bigger",
        "--command": "Format ▸ Smaller",
    ]

    @Test("no two different commands claim the same shortcut, across the whole app")
    func noTwoCommandsShareAChord() throws {
        let mints = try allMints()
        #expect(!mints.isEmpty, "found no shortcut mints — the scan root or patterns are wrong")

        var filesByChord: [String: Set<String>] = [:]
        var sitesByChord: [String: [Mint]] = [:]
        for mint in mints {
            let chord = "\(mint.key)-\(mint.modifiers)"
            filesByChord[chord, default: []].insert(mint.file)
            sitesByChord[chord, default: []].append(mint)
        }

        for (chord, files) in filesByChord where files.count > 1 && !Self.allowedSharedChords.contains(chord) {
            let sites = sitesByChord[chord, default: []]
                .map { "\($0.file):\($0.line)" }
                .sorted()
                .joined(separator: ", ")
            let detail: String = "Shortcut \(chord) is bound by \(files.count) different files — \(sites). "
                + "Two commands sharing one chord means the wrong one can fire (the ⌘⌥1→loupe bug class)."
            Issue.record("\(detail)")
        }
        let collisions = filesByChord.keys
            .filter { (filesByChord[$0]?.count ?? 0) > 1 && !Self.allowedSharedChords.contains($0) }
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
