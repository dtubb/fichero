@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// spec: panes-magnifiers-workspaces §"v2 workspace design" + §"Accessibility is first-class"
/// (`workspaces.one-system`, ⌘⌥1–6 reachability) AND the shortcut-collision bug the CD hit live
/// (2026-09-16): "⌘⌥1 opens the LOUPE instead of applying the Read workspace." A workspace slot and
/// a magnifier verb (or ANY two commands) sharing one ⌘⌥ chord is a defect — the wrong command
/// fires. These tests enumerate the ⌘⌥ chords the app mints and assert every one is UNIQUE, so a
/// double-binding fails the suite instead of shipping as a live mis-fire.
///
/// Two layers, because the shortcuts are not all reachable as one datum:
///   1. the workspace slots ARE data (`WorkspaceCommandsSection.shortcut(for:)`), asserted directly;
///   2. every OTHER ⌘⌥ chord is a `.keyboardShortcut("x", modifiers: [.command, .option])` literal
///      scattered across View bodies (loupe, magnifier, reader-find, immersive reading, markup
///      tools). Those are not queryable as runtime data, so this scans the app source for the exact
///      literal and asserts no key+modifier pair is claimed by two different commands.
struct MenuShortcutUniquenessTests {

    // MARK: - 1. The workspace slots are ⌘⌥1–6, unique, and never the loupe's ⌘⌥L

    /// spec workspaces.one-system + §"the slot→workspace map": ⌘⌥1–6 map to the six built-ins in
    /// declaration order, all six chords distinct, and NONE collides with the loupe's ⌘⌥L
    /// (ImagePreviewMenuCommands.swift:139). This is the model half of the "⌘⌥1 opened the loupe"
    /// bug: it pins that the workspace slot chords are exactly the digits under ⌘⌥ and share no key
    /// with the magnifier family.
    @Test("⌘⌥1–6 map to the six workspaces, all distinct, none is the loupe's ⌘⌥L")
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
            // The loupe is ⌘⌥L (ImagePreviewMenuCommands.swift:139). A workspace slot minted as "l"
            // would be the exact collision the CD saw; assert the slot key is never the loupe's.
            #expect(
                shortcut.key.character != "l",
                "\(layout.title) minted ⌘⌥L — the loupe's chord (the reported ⌘⌥1→loupe mis-fire)"
            )
            let token = chordToken(shortcut)
            #expect(!seen.contains(token), "\(layout.title) reuses the ⌘⌥ chord \(token)")
            seen.insert(token)
        }
        #expect(seen.count == BuiltInWorkspaceLayout.allCases.count, "the six slots must be six distinct chords")
    }

    private func chordToken(_ shortcut: KeyboardShortcut) -> String {
        "\(shortcut.key.character)-\(shortcut.modifiers.rawValue)"
    }

    // MARK: - 2. No two commands share a ⌘⌥ key+modifiers (source-scan)

    /// A single ⌘⌥ literal chord: which file + line minted it, and the key character.
    private struct Chord: Hashable {
        let file: String
        let line: Int
        let key: String
    }

    /// spec: the shortcut-uniqueness ruling — no two commands may claim the same ⌘⌥ key. Scans the
    /// WHOLE app source (comments stripped) for `.keyboardShortcut("x", modifiers: [.command,
    /// .option])` literals — the loupe/magnifier/markup/reader chords — and asserts each key belongs
    /// to exactly ONE file. Today this FAILS: ⌘⌥F is minted twice — "Find in Artifact"
    /// (ViewMenuPaneSections.swift, ShowFindBarButton) and "Enter Full-Screen Reading"
    /// (ContentView+RootLayout.swift). Two commands, one chord ⇒ the wrong one can fire, exactly the
    /// bug class of "⌘⌥1 opened the loupe."
    ///
    /// NOTE (testable-seam): the chords live in SwiftUI View bodies, not in a reachable table, so
    /// this asserts them by scanning the literal. The clean fix the manager can make is a single
    /// `AppKeyboardShortcuts` registry the menus read from — then this test asserts the registry
    /// (data), not the source text. Dynamic mints (the workspace `KeyEquivalent(String(number))`,
    /// the markup `toolButton(key:)`) are folded in separately below rather than scanned.
    @Test("no ⌘⌥ chord is claimed by two different commands")
    func noTwoCommandsShareACommandOptionChord() throws {
        let chords = try commandOptionLiteralChords()
        #expect(!chords.isEmpty, "found no ⌘⌥ literal chords — the scan regex or root is wrong")

        // Group by key; a key claimed in more than one FILE is a genuine cross-command collision.
        // (The same file listing a key twice is the #if/#else twin of ONE button — e.g.
        // ShowFindBarButton's AppKit/else branches both write ⌘⌥F — not a collision.)
        var filesByKey: [String: Set<String>] = [:]
        var sitesByKey: [String: [Chord]] = [:]
        for chord in chords {
            filesByKey[chord.key, default: []].insert(chord.file)
            sitesByKey[chord.key, default: []].append(chord)
        }

        for (key, files) in filesByKey where files.count > 1 {
            let sites = sitesByKey[key, default: []]
                .map { "\($0.file):\($0.line)" }
                .sorted()
                .joined(separator: ", ")
            Issue.record(
                "⌘⌥\(key.uppercased()) is bound by \(files.count) different commands — \(sites). Two commands sharing one ⌘⌥ chord means the wrong one can fire (the ⌘⌥1→loupe bug class). Give each command its own chord (spec: shortcut uniqueness)."
            )
        }
        let collisions = filesByKey.filter { $0.value.count > 1 }.keys.sorted()
        #expect(collisions.isEmpty, "colliding ⌘⌥ chords: \(collisions.map { "⌘⌥\($0.uppercased())" })")
    }

    /// spec: the workspace slots (⌘⌥1–6, minted dynamically) must not collide with any STATIC ⌘⌥
    /// literal chord. Folds the two enumerations together — the data slots and the scanned literals
    /// — so a future `.keyboardShortcut("1", modifiers: [.command, .option])` added anywhere would
    /// fail against the Read workspace's ⌘⌥1.
    @Test("no static ⌘⌥ literal collides with a workspace slot ⌘⌥1–6")
    func staticChordsNeverCollideWithWorkspaceSlots() throws {
        let slotKeys = Set(
            BuiltInWorkspaceLayout.allCases.compactMap {
                WorkspaceCommandsSection.shortcut(for: $0).map { String($0.key.character) }
            }
        )
        let literalKeys = Set(try commandOptionLiteralChords().map(\.key))
        let overlap = slotKeys.intersection(literalKeys).sorted()
        #expect(
            overlap.isEmpty,
            "static ⌘⌥ literals collide with workspace slots ⌘⌥\(overlap.joined(separator: ",")) — the exact 'workspace shortcut fires the wrong command' defect (spec workspaces.one-system)."
        )
    }

    // MARK: - Source scan

    /// Every `.keyboardShortcut("x", modifiers: [.command, .option])` literal in the app (comments
    /// stripped). The regex requires the modifier array to CLOSE right after `.option`, so ⌘⌥⇧ and
    /// ⌃⌥⌘ chords (Show Workflow Bar, Representation) are correctly excluded — only the exact
    /// command+option pair matches.
    private func commandOptionLiteralChords() throws -> [Chord] {
        let root = try AppSource.root().standardizedFileURL
        guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil) else {
            return []
        }
        let pattern = #"keyboardShortcut\("(.)",\s*modifiers:\s*\[\.command,\s*\.option\]\)"#
        let regex = try NSRegularExpression(pattern: pattern)

        var chords: [Chord] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            let source = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            for (index, rawLine) in source.components(separatedBy: .newlines).enumerated() {
                // Skip comment-only lines so a commented-out chord (or an explanatory comment naming
                // one) never counts — but keep the raw index so failures cite the real file line.
                if rawLine.trimmingCharacters(in: .whitespaces).hasPrefix("//") { continue }
                let range = NSRange(rawLine.startIndex..<rawLine.endIndex, in: rawLine)
                regex.enumerateMatches(in: rawLine, range: range) { match, _, _ in
                    guard let match, let keyRange = Range(match.range(at: 1), in: rawLine) else { return }
                    chords.append(Chord(file: relative, line: index + 1, key: String(rawLine[keyRange])))
                }
            }
        }
        return chords
    }
}
