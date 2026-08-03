import XCTest

/// Guards for #4461 (the #4306 class): a DOCUMENT-scoped surface must resolve
/// its services from the library that owns the document, never from
/// `globalLibrary`.
///
/// The failure this exists to stop is quiet. A document surface that asks the
/// global library for a service gets *a* real answer — a prototype list, a
/// claim set, a document name — just from the wrong library. Nothing throws,
/// nothing logs, and in the global library (the one a developer usually has
/// open) it is indistinguishable from correct. #4306 only surfaced because
/// translate happened to ERROR when the document was absent; the sibling reads
/// degraded silently for months.
///
/// So this is a source-level lint, per the issue's own suggestion: make the
/// reach grep-able rather than a judgment call, with the deliberate exceptions
/// named and reasoned in one place.
final class DocumentScopeGuardTests: XCTestCase {

    // MARK: - What counts as a document surface

    /// Directories whose contents exist to show or edit ONE document (or one
    /// claim/artifact/entity belonging to documents). Scanned wholesale rather
    /// than file-by-file so a future split cannot quietly drop a file out of
    /// coverage — the #4160 lesson from `CanvasStorageScopingGuardTests`.
    ///
    /// `Views/Library/ViewModes/Graph` is NOT here. That cluster is coherently
    /// global-only today (25 unconditional `globalLibrary` lines across the
    /// ontology browser, the map, the timeline and every entity sheet), and
    /// correcting a card inside it while its host stays global would put two
    /// scopes in one window — a worse failure than one consistent wrong one.
    /// It needs a single deliberate pass, tracked separately.
    ///
    /// COVERAGE LIMIT, stated rather than implied: `Views/Library` is also not
    /// scanned wholesale. Outside the Graph subtree it still holds six
    /// `globalLibrary` lines (the batch-workflow run in `DocumentPickerSheet`,
    /// the 3D canvas storage fallback in `SpaceSceneView`, two automation
    /// previews, and two resolution-first accessors). Each needs reading before
    /// it is either fixed or allowlisted, and allowlisting a line nobody has
    /// read is how a guard becomes a rubber stamp. The one #4461 fix in that
    /// directory — the inline rename — is asserted directly below instead.
    private static let documentSurfaceDirectories = [
        "Views/Inspector",
        "Views/Reader",
        "Views/Preview"
    ]

    /// Files inside a document surface that may name `globalLibrary` outright,
    /// each with the reason global is the CORRECT scope there. Forced
    /// uniformity where the app legitimately differs would be a new bug, so
    /// these are exceptions with reasons, not suppressions.
    ///
    /// Every entry is verified to still exist (`testAllowlistHasNoStaleEntries`)
    /// so this cannot rot into a permanent amnesty for deleted code.
    private static let allowed: [String: String] = [
        // Workflows are global-only by construction — the sidebar renders them
        // only when `libraryId == LibraryManager.globalLibraryId`. A pane
        // listing workflows is asking an app-level question, not a document one.
        "Views/Inspector/Artifacts/ArtifactsInspectorPane.swift":
            "workflowStore: workflows are gated to the global library",

        // `#Preview` scaffolding, not shipped behaviour.
        "Views/Inspector/Document/DocumentInspector.swift":
            "#Preview bodies only",

        // Both resolve the window's library FIRST and return global only when
        // nothing is open. That is a last resort, not a reach.
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift":
            "currentLibrary: window library first, global as last resort",
        "Views/Inspector/FocusedDocument.swift":
            "activeLibrary: focused library first, global as last resort"
    ]

    // MARK: - The detector

    /// Whether one line of source is a document-scoped reach for a global
    /// service. Pure and total so the fixtures below can exercise it directly —
    /// a guard whose detector is only ever run over the real tree can pass
    /// green because it detects nothing at all.
    static func isGlobalServiceReach(_ line: String) -> Bool {
        guard line.contains("globalLibrary") else { return false }
        // `LibraryManager.globalLibraryId` is a UUID default for a navigation
        // payload, not a service lookup.
        if line.replacingOccurrences(of: "globalLibraryId", with: "").contains("globalLibrary") == false {
            return false
        }
        // `x ?? libraryManager.globalLibrary` means the caller already tried to
        // resolve its own library; global is the fallback, which is allowed.
        if line.contains("??") { return false }
        // A comment naming the rule is not a violation of it.
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("//") || trimmed.hasPrefix("///") || trimmed.hasPrefix("*") {
            return false
        }
        return true
    }

    // MARK: - Fixtures: prove the detector FIRES

    func testDetectorFlagsAnUnconditionalReach() {
        XCTAssertTrue(
            Self.isGlobalServiceReach(
                "        guard let svc = LibraryManager.shared.globalLibrary?.entityService else { return }"
            ),
            "The exact #4461 shape must be flagged — otherwise this suite is decoration."
        )
        XCTAssertTrue(
            Self.isGlobalServiceReach("        let library = libraryManager.globalLibrary!"),
            "A force-unwrapped global reach must be flagged too."
        )
    }

    func testDetectorAcceptsTheLegitimateShapes() {
        XCTAssertFalse(
            Self.isGlobalServiceReach(
                "        libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary"
            ),
            "Resolution-first with a global fallback is correct and must not be flagged."
        )
        XCTAssertFalse(
            Self.isGlobalServiceReach(
                "        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId"
            ),
            "A globalLibraryId default is an id, not a service reach."
        )
        XCTAssertFalse(
            Self.isGlobalServiceReach("        // Reaching for globalLibrary here was #4306."),
            "A comment naming the rule must not trip it."
        )
        XCTAssertFalse(
            Self.isGlobalServiceReach("        let library = libraryManager.library(atPath: path)"),
            "A correctly-scoped lookup must not be flagged."
        )
    }

    // MARK: - The scan

    func testNoDocumentSurfaceReachesForGlobalLibrary() throws {
        let scan = try Self.scanDocumentSurfaces()

        // Population floor (#4487): a scan that found no files, or found files
        // but never saw the token it hunts, is BLIND, not clean. Without this
        // a mis-rooted or over-filtered scan reports success forever.
        XCTAssertGreaterThan(
            scan.filesScanned, 40,
            "BLIND: scanned \(scan.filesScanned) files across \(Self.documentSurfaceDirectories). "
                + "The document surfaces are far larger than that — the scan is not reaching the tree."
        )
        XCTAssertGreaterThan(
            scan.globalLibraryMentions, 0,
            "BLIND: not one 'globalLibrary' mention in any document surface. The allowlisted files "
                + "below all contain one, so zero means the reader, not the app, changed."
        )

        XCTAssertTrue(
            scan.violations.isEmpty,
            """
            Document-scoped surfaces must not reach for globalLibrary (#4461, the #4306 class).
            A document surface asking the global library for a service returns a real answer from
            the WRONG library — worse than an error, because nothing surfaces it.

            Resolve the owning library instead:
              LibraryManager.shared.library(owningService: <the injected service>)
            or take it from the parent that already knows (see DocumentInspectorInfoTab, which
            hands `currentLibrary` down to RelatedClaimsPanel and DocumentPrototypePicker).

            If global genuinely IS the right scope here, add the file to `allowed` above WITH the
            reason — an app-wide concern is not a bug, and forcing uniformity onto one would be.

            \(scan.violations.joined(separator: "\n"))
            """
        )
    }

    func testAllowlistHasNoStaleEntries() throws {
        let root = try AppSource.root()
        for path in Self.allowed.keys {
            XCTAssertTrue(
                FileManager.default.fileExists(atPath: root.appendingPathComponent(path).path),
                "Allowlisted file no longer exists: \(path). A stale entry is a standing amnesty "
                    + "for whatever takes that path next — delete it."
            )
            let source = try String(
                contentsOf: root.appendingPathComponent(path), encoding: .utf8
            )
            XCTAssertTrue(
                source.contains("globalLibrary"),
                "\(path) is allowlisted but no longer mentions globalLibrary — remove the exception."
            )
        }
    }

    // MARK: - The rename is a WRITE, and it must hit the window's library

    /// `LibraryView` renamed through `globalLibrary.documentStore` while the
    /// user was looking at whatever library the window shows — the #4306 reach,
    /// except this one MUTATES. The correct accessor already existed on the
    /// same type; the rename simply never used it. Asserted by name because
    /// `Views/Library` is not scanned wholesale (see the coverage note above).
    func testInlineRenameUsesTheWindowsLibrary() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Library/LibraryView+InlineEditing.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(
            source.contains("guard let library = activeLibraryReference else { return }"),
            "commitRename must resolve the WINDOW's library (#4461) — renaming through "
                + "globalLibrary writes to a database the document is not in."
        )
        XCTAssertFalse(
            source.contains("guard let library = libraryManager.globalLibrary"),
            "The global reach must not come back."
        )
    }

    // MARK: - vendedServices stays exhaustive

    /// `library(owningService:)` can only match a service that
    /// `vendedServices` lists. A service declared on `LibraryReference` but
    /// missing there resolves to nil, and a surface holding it silently loses
    /// its scope — the #4411 shape exactly: a derived list that nothing forces
    /// to track its own inputs.
    func testVendedServicesCoversEveryDeclaredService() throws {
        let root = try AppSource.root()
        let manager = try String(
            contentsOf: root.appendingPathComponent("Models/LibraryManager.swift"), encoding: .utf8
        )
        let scope = try String(
            contentsOf: root.appendingPathComponent("Models/LibraryManager+Scope.swift"), encoding: .utf8
        )

        var declared: [String] = []
        for line in manager.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix("let "), trimmed.contains(":") else { continue }
            let name = String(trimmed.dropFirst(4).prefix(while: { $0 != ":" }))
                .trimmingCharacters(in: .whitespaces)
            guard name.hasSuffix("Service") || name.hasSuffix("Store") || name.hasSuffix("Client")
            else { continue }
            declared.append(name)
        }

        XCTAssertGreaterThan(
            declared.count, 20,
            "BLIND: parsed \(declared.count) service declarations off LibraryReference. "
                + "The type declares far more — the parser stopped matching, so this guard proves nothing."
        )

        let missing = declared.filter { name in
            !scope.contains("            \(name),") && !scope.contains("            \(name)\n")
        }
        XCTAssertTrue(
            missing.isEmpty,
            "vendedServices is missing \(missing.joined(separator: ", ")). Append them in "
                + "LibraryManager+Scope.swift — a service that is not listed cannot be resolved "
                + "back to its library, and a view injected with it loses its scope silently."
        )
    }

    // MARK: - Scanning

    private struct Scan {
        var filesScanned = 0
        var globalLibraryMentions = 0
        var violations: [String] = []
    }

    private static func scanDocumentSurfaces() throws -> Scan {
        let root = try AppSource.root()
        var scan = Scan()

        for directory in documentSurfaceDirectories {
            let base = root.appendingPathComponent(directory)
            let subpaths = (try? FileManager.default.subpathsOfDirectory(atPath: base.path)) ?? []
            for subpath in subpaths where subpath.hasSuffix(".swift") {
                // Build products are not source. They exist only in a worktree
                // that has been built, so including them makes the guard's
                // verdict depend on whether someone ran a build here.
                if subpath.contains(".build/") || subpath.contains("DerivedData/") { continue }

                let relative = "\(directory)/\(subpath)"
                let source = try String(
                    contentsOf: base.appendingPathComponent(subpath), encoding: .utf8
                )
                scan.filesScanned += 1
                if source.contains("globalLibrary") { scan.globalLibraryMentions += 1 }
                if allowed[relative] != nil { continue }

                for (index, line) in source.components(separatedBy: .newlines).enumerated()
                where isGlobalServiceReach(line) {
                    scan.violations.append(
                        "  \(relative):\(index + 1)  \(line.trimmingCharacters(in: .whitespaces))"
                    )
                }
            }
        }
        return scan
    }
}
