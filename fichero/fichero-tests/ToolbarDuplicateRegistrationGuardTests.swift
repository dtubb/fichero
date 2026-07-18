import XCTest

/// Source-surface regression guard for the #3163 NSToolbar duplicate-identifier
/// launch crash (`EXC_BREAKPOINT` in
/// `-[NSToolbar _insertNewItemWithItemIdentifier:…]`), deterministic and
/// headless — no running app needed (mirrors `ShellLayoutGuardTests`).
///
/// The crash class has two members, both guarded here:
///
/// 1. **Duplicate search registration** — two `.searchable` modifiers reaching
///    one window's NSToolbar collide on the fixed identifier
///    `com.apple.SwiftUI.search` ("Duplicate items not allowed"). The invariant:
///    ONLY ContentView registers the global toolbar search
///    (`ToolbarSearchableModifier`, #3037); mode views (Workflows / Chains /
///    Actions / Search / Library — and any FUTURE feature-gated view that
///    becomes reachable with `fichero.features.all_enabled`) must NOT apply
///    their own `.searchable`. The 2026.07.07-beta crash fired exactly this
///    way: with all feature flags on, a newly-reachable mode view's bare
///    `.searchable` merged into the same NSToolbar as ContentView's global one.
///
/// 2. **Re-entrant sheet during the toolbar's first layout** — auto-presenting
///    a sheet in the same update cycle that flips `isBackendRunning` (when
///    ContentView mounts and the NSToolbar does its first full layout)
///    re-enters the toolbar update and double-inserts an item. The AddProvider
///    sheet fix lives in `AppState.loadProviders`; the FirstRunWindow sheet is
///    deferred via `firstRunSheetArmed` in `LibraryWindow`.
final class ToolbarDuplicateRegistrationGuardTests: XCTestCase {

    // MARK: - Source loading

    /// App-target source root: fichero/fichero (this file lives in
    /// fichero/fichero-tests, a sibling of the app folder).
    private static var appSourceRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero (project dir)
            .appendingPathComponent("fichero")
    }

    /// Every .swift file in the app target, path relative to the source root.
    private static func appSwiftFiles() throws -> [(path: String, source: String)] {
        let root = appSourceRoot
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
        ) else {
            XCTFail("Could not enumerate app sources at \(root.path)")
            return []
        }
        var files: [(String, String)] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let source = try String(contentsOf: url, encoding: .utf8)
            let relative = url.path.replacingOccurrences(of: root.path + "/", with: "")
            files.append((relative, source))
        }
        XCTAssertFalse(files.isEmpty, "No app sources found under \(root.path)")
        return files
    }

    /// The line with any trailing `//` comment stripped; nil for whole-line
    /// comments. Good enough to keep prose mentions of `.searchable` (of which
    /// this codebase has many, in #3163 comments) from tripping the guard.
    private static func liveCode(in line: Substring) -> Substring? {
        let trimmed = line.drop(while: { $0 == " " || $0 == "\t" })
        if trimmed.hasPrefix("//") { return nil }
        if let commentStart = line.range(of: "//") {
            return line[line.startIndex..<commentStart.lowerBound]
        }
        return line
    }

    /// All live-code lines of `source` containing `needle`.
    private static func liveOccurrences(of needle: String, in source: String) -> Int {
        source.split(separator: "\n", omittingEmptySubsequences: false)
            .compactMap(liveCode(in:))
            .filter { $0.contains(needle) }
            .count
    }

    // MARK: - 1. Single global .searchable

    /// Only ContentView (the global `ToolbarSearchableModifier`) and the
    /// MiniToolbar helper that DEFINES `conditionalSearchable` may contain a
    /// live `.searchable(` call. Any other file — in particular a mode view
    /// that becomes reachable when all feature flags are on — re-registers
    /// `com.apple.SwiftUI.search` on the same NSToolbar and crashes (#3163).
    func testOnlyContentViewRegistersToolbarSearchable() throws {
        let allowlist: [String: Int] = [
            "Views/ContentView.swift": 1,          // ToolbarSearchableModifier (#3037)
            "Views/Toolbars/MiniToolbar.swift": 1  // conditionalSearchable's definition
        ]

        for (path, source) in try Self.appSwiftFiles() {
            let count = Self.liveOccurrences(of: ".searchable(", in: source)
            if let allowed = allowlist[path] {
                XCTAssertLessThanOrEqual(
                    count, allowed,
                    "\(path) grew an extra .searchable — ContentView owns the SINGLE "
                        + "global toolbar search; a second registration duplicates "
                        + "com.apple.SwiftUI.search on the window NSToolbar and "
                        + "crashes at launch (#3163)."
                )
            } else {
                XCTAssertEqual(
                    count, 0,
                    "\(path) registers .searchable. Mode views must NOT own a toolbar "
                        + "search — ContentView's global .searchable "
                        + "(ToolbarSearchableModifier) is the only one per window; a "
                        + "duplicate com.apple.SwiftUI.search crashes NSToolbar at "
                        + "launch, and feature-gated views hit it the moment "
                        + "fichero.features.all_enabled makes them reachable (#3163). "
                        + "Route search through ContentView (toolbarSearchText) instead."
                )
            }
        }
    }

    /// `conditionalSearchable` (the split-pane-gated variant) is defined in
    /// MiniToolbar.swift and currently has NO call sites — the per-view toolbar
    /// searches it once gated were removed outright (9f62791f3/#3163: "search
    /// in toolbar is always for files"). A new call site would re-introduce a
    /// second toolbar search alongside ContentView's global one, which is the
    /// crash, split pane or not.
    func testNoModeViewRevivesConditionalSearchable() throws {
        for (path, source) in try Self.appSwiftFiles()
        where path != "Views/Toolbars/MiniToolbar.swift" {
            XCTAssertEqual(
                Self.liveOccurrences(of: ".conditionalSearchable(", in: source), 0,
                "\(path) calls conditionalSearchable — even gated to the primary "
                    + "split pane, this registers a SECOND toolbar search next to "
                    + "ContentView's global one (duplicate com.apple.SwiftUI.search "
                    + "→ #3163 launch crash). Use ContentView's global search."
            )
        }
    }

    // MARK: - 2. Fixed toolbar-item ids are unique per window

    /// Every explicit `ToolbarItem(id: …)` id must be registered by exactly
    /// one view. Two views contributing the same fixed id to the merged window
    /// toolbar is the same NSToolbar duplicate-identifier crash. Within a
    /// single file a repeated id is allowed ONLY for ContentView's
    /// `fichero.inspectorToggle`, whose two occurrences are `#if os(visionOS)`
    /// / `#else` — compile-time exclusive.
    func testNoDuplicateFixedToolbarItemIdsAcrossViews() throws {
        // id → files that register it (with per-file counts)
        var registrations: [String: [String: Int]] = [:]
        let idPattern = try NSRegularExpression(
            pattern: #"ToolbarItem\(id:\s*([A-Za-z_][A-Za-z0-9_.]*)"#
        )

        for (path, source) in try Self.appSwiftFiles() {
            for line in source.split(separator: "\n", omittingEmptySubsequences: false) {
                guard let code = Self.liveCode(in: line) else { continue }
                let codeString = String(code)
                let range = NSRange(codeString.startIndex..., in: codeString)
                for match in idPattern.matches(in: codeString, range: range) {
                    guard let idRange = Range(match.range(at: 1), in: codeString) else { continue }
                    let id = String(codeString[idRange])
                    registrations[id, default: [:]][path, default: 0] += 1
                }
            }
        }

        XCTAssertFalse(registrations.isEmpty, "Expected ContentView's fixed toolbar-item ids to be found")

        // Compile-time-exclusive pairs (`#if` platform branches) in ONE file.
        let sameFileAllowlist: Set<String> = ["ContentToolbarID.inspectorToggle"]

        for (id, files) in registrations {
            XCTAssertEqual(
                files.count, 1,
                "Toolbar item id \"\(id)\" is registered by multiple views "
                    + "(\(files.keys.sorted().joined(separator: ", "))). All those "
                    + "toolbars merge into ONE window NSToolbar — a duplicate id "
                    + "throws in _insertNewItemWithItemIdentifier and crashes the "
                    + "app (#3163 class). Only ContentView registers the global "
                    + "toolbar items; mode views must not re-register them."
            )
            for (path, count) in files where count > 1 {
                XCTAssertTrue(
                    sameFileAllowlist.contains(id),
                    "Toolbar item id \"\(id)\" appears \(count)× in \(path). Unless "
                        + "the occurrences are compile-time exclusive (#if platform "
                        + "branches, like ContentView's fichero.inspectorToggle), "
                        + "they double-insert into the window NSToolbar and crash "
                        + "(#3163 class)."
                )
            }
        }
    }

    // MARK: - 3. No sheet auto-presents during the toolbar's first layout

    /// The FirstRunWindow sheet must stay gated on `firstRunSheetArmed`, which
    /// trails the `isBackendRunning` flip by a settle beat. Presenting it in
    /// the same update cycle that mounts ContentView re-enters the NSToolbar's
    /// first layout and double-inserts an item — the launch crash the
    /// AddProvider sheet already hit and fixed (#3163, AppState.loadProviders).
    func testFirstRunSheetIsDeferredPastFirstToolbarLayout() throws {
        let source = try String(
            contentsOf: Self.appSourceRoot
                .appendingPathComponent("App")
                .appendingPathComponent("LibraryWindow.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(
            source.contains(
                "firstRunSheetArmed && appState.isBackendRunning && !featureManager.firstRunCompleted"
            ),
            "LibraryWindow's first-run sheet must be gated on firstRunSheetArmed "
                + "so it never presents in the same update cycle that flips "
                + "isBackendRunning — that cycle mounts ContentView and runs the "
                + "NSToolbar's FIRST layout; presenting mid-layout re-enters the "
                + "toolbar update and double-inserts an item (#3163 launch crash)."
        )
        XCTAssertTrue(
            source.contains(".task(id: appState.isBackendRunning)"),
            "LibraryWindow must arm firstRunSheetArmed via a deferred task keyed "
                + "on isBackendRunning (settle beat after backend-ready), so the "
                + "first-run sheet misses the toolbar's first-layout window (#3163)."
        )
    }
}
