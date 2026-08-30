@testable import Fichero
import XCTest

/// Every inspector action must have a route that exists without a mouse (#4505).
///
/// These live in the MAC test target, not the iPad one, and that placement is
/// the point rather than a compromise. They read SOURCE — which affordances a
/// file mounts — via `AppSource`, which resolves the tree from `#filePath`. On
/// a simulator that path exists because it is the same machine; on a real iPad
/// it does not. A source-reading test in a device-capable target is a test that
/// silently stops working the moment somebody runs it on hardware.
///
/// So the split is: facts about SOURCE are checked here (and swept repo-wide by
/// `scripts/check_touch_reachable_actions.py`); facts that need an iPad at
/// RUNTIME live in `FicheroIPadTests`. The first version of this file put both
/// in the iPad target, which would not even have compiled there — `AppSource`
/// belongs to `fichero-tests` and the iPad target has its own synchronized
/// folder.
final class InspectorTouchReachabilityTests: XCTestCase {

    // MARK: - Every action needs a route that exists without a mouse

    /// `openEntity` had exactly one caller: the row's `TapGesture(count: 2)`.
    /// iPad has no double-click, so opening an entity was unreachable there.
    func testOpeningAnEntityIsReachableWithoutADoubleClick() throws {
        let source = try AppSource.text(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Menus.swift"
        )

        XCTAssertTrue(
            source.contains(#"Button("Open") { openEntity(entity) }"#),
            "the entity context menu must offer Open; double-click is Mac-only"
        )
    }

    /// `openClaim` likewise — and this one matters more, because #4393's whole
    /// argument is that a claim must be traceable back to the page it came
    /// from. On iPad that trace did not exist.
    func testOpeningAClaimSourceIsReachableWithoutADoubleClick() throws {
        let source = try AppSource.text(
            "Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift"
        )

        XCTAssertTrue(source.contains(#"Button("Open Source")"#))
        XCTAssertTrue(
            source.contains("openClaim(claimId: claimId, sourceDocumentId: sourceDocumentId)"),
            "the menu item must invoke the same action the double-click does"
        )
    }

    /// The third site was already fine, and saying so matters as much as the
    /// two fixes: `ArtifactListView` pairs its double-click with a context-menu
    /// item, which is why it is the pattern the other two were repaired to.
    /// The audit flagged all three as suspicious; only two were defects.
    func testTheArtifactRowAlreadyHadItsFallback() throws {
        let source = try AppSource.text("Views/Inspector/Artifacts/ArtifactListView.swift")

        XCTAssertTrue(source.contains(#"Button("Open in Window")"#))
    }

    // MARK: - A button that does nothing is worse than an absent one

    /// "Copy Name" was wrapped in `#if canImport(AppKit)`, so on iPad the
    /// Button rendered with an EMPTY body — a menu item that does nothing,
    /// which is exactly the shape #4421's standing rule forbids.
    /// `PlatformPasteboard` already existed and its own doc comment says not to
    /// reach into `NSPasteboard`/`UIPasteboard` from view code.
    func testCopyNameActuallyCopiesOnIPad() throws {
        let source = try AppSource.text(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Menus.swift"
        )

        XCTAssertTrue(source.contains("PlatformPasteboard.writeString(entity.canonicalName)"))
        // Comments stripped: the file's own note explains why it no longer
        // touches NSPasteboard, and matching raw source would fail on that
        // prose. Third time tonight a rule has fired on its own explanation,
        // so it is worth stating plainly — a check about CODE must read code.
        XCTAssertFalse(
            Self.code(of: source).contains("NSPasteboard"),
            "view code must go through PlatformPasteboard, or the action is Mac-only"
        )
    }

    /// Source with `//` line comments removed.
    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }

    // MARK: - Delete

    /// Delete on the artifact list is `onDeleteCommand` (a hardware ⌫, absent
    /// on iPad) PLUS a context-menu item. The menu is what makes it reachable
    /// here, so it must not be removed on the grounds that "delete already
    /// exists".
    func testDeletingAnArtifactIsReachableWithoutAKeyboard() throws {
        let source = try AppSource.text("Views/Inspector/Artifacts/ArtifactListView.swift")

        XCTAssertTrue(source.contains("onDeleteCommand"), "premise changed; re-check this test")
        XCTAssertTrue(
            source.contains(#"Button("Delete", role: .destructive)"#),
            "onDeleteCommand is keyboard-only; iPad needs the menu item"
        )
    }

    // MARK: - What this target still cannot check

    /// Recorded as a test so it is in the run output rather than in a document
    /// nobody opens. It always passes; its job is to name the gap.
    ///
    /// Unverifiable without a UI-test target that can drive the app:
    ///   1. 44pt minimum touch targets on inspector rows.
    ///   2. Whether a long-press context menu actually opens on each row.
    ///   3. Whether the compact-width inspector's CONTENTS are usable —
    ///      `DocumentInspector` reads no `horizontalSizeClass`, so only the
    ///      container adapts, and that is a layout judgement, not a predicate.
    ///
    /// `FicheroIPadTests` is a unit-test bundle; none of the three is a unit.
    func testUnverifiableWithoutAUITestTarget() throws {
        let inspector = try AppSource.text("Views/Inspector/Document/DocumentInspector.swift")

        // The one part of (3) that IS a fact about source, pinned so the claim
        // in the audit stays true or fails here.
        XCTAssertFalse(
            inspector.contains("horizontalSizeClass"),
            """
            DocumentInspector now reads the size class — the audit's claim that \
            only the CONTAINER adapts is out of date; re-check what the contents do.
            """
        )
    }
}
