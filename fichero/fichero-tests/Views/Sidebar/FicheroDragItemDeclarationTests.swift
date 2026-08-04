import Foundation
import UniformTypeIdentifiers
import XCTest

@testable import Fichero

/// The in-app drag flavor's identifier must be DECLARED, not merely named.
///
/// `UTType.ficheroDragItem` is created with `UTType(exportedAs:)` — documented
/// as "a type your app owns", whose ownership an app declares in Info.plist
/// under `UTExportedTypeDeclarations`. The identifier was never declared, and
/// the failure was invisible to every unit test: a provider CONSTRUCTED in a
/// test carries whatever identifier it is given, but a REAL drag rides the
/// system pasteboard, which degraded the undeclared identifier to its bare
/// `public.data` conformance (empirical, live-repro 2026-08-04). The reader
/// then classified an in-app .tif drag as external files and re-imported it as
/// a hollow duplicate — #4401's shape, third occurrence.
///
/// A live drag is the only true end-to-end check, so this pin does the next
/// best thing: it asserts the declaration EXISTS in the app's Info.plist and
/// names the SAME identifier the code exports, so the two can never drift
/// apart silently again.
final class FicheroDragItemDeclarationTests: XCTestCase {

    private func exportedDeclarations() throws -> [[String: Any]] {
        let plistURL = try AppSource.root().appendingPathComponent("Info.plist")
        let data = try Data(contentsOf: plistURL)
        let plist = try PropertyListSerialization.propertyList(from: data, format: nil)
        let root = try XCTUnwrap(plist as? [String: Any])
        return try XCTUnwrap(
            root["UTExportedTypeDeclarations"] as? [[String: Any]],
            "fichero/Info.plist lost its UTExportedTypeDeclarations array"
        )
    }

    func testTheDragItemIdentifierIsDeclaredInTheAppInfoPlist() throws {
        let declarations = try exportedDeclarations()
        let dragDeclaration = declarations.first {
            $0["UTTypeIdentifier"] as? String == UTType.ficheroDragItem.identifier
        }
        XCTAssertNotNil(
            dragDeclaration,
            """
            \(UTType.ficheroDragItem.identifier) is not declared in \
            fichero/Info.plist UTExportedTypeDeclarations. Undeclared custom \
            identifiers degrade to bare public.data on the real drag \
            pasteboard, and in-app drags get re-imported as duplicates.
            """
        )
        let conforms = try XCTUnwrap(dragDeclaration?["UTTypeConformsTo"] as? [String])
        XCTAssertTrue(
            conforms.contains(UTType.data.identifier),
            "the declaration must conform to public.data — the conformance every [.item]/[.data] drop list relies on"
        )
    }

    /// The .fichero library package declaration must survive edits to the same
    /// array — it is what lets a library open by double-click.
    func testTheLibraryPackageDeclarationIsStillPresent() throws {
        let declarations = try exportedDeclarations()
        XCTAssertTrue(
            declarations.contains { $0["UTTypeIdentifier"] as? String == "app.fichero.fichero.library" },
            "fichero/Info.plist lost the app.fichero.fichero.library package declaration"
        )
    }

    /// The stale generated build setting this fix replaced declared
    /// `com.tubb.fichero.item` — an identifier nothing exports. It must not
    /// come back: with `GENERATE_INFOPLIST_FILE = YES` a generated
    /// `UTExportedTypeDeclarations` that disagrees with the file is at best
    /// inert and at worst clobbers the file's array, depending on merge
    /// precedence nobody should have to remember.
    func testNoStaleIdentifierAnywhereInTheProjectFile() throws {
        let projectURL = try AppSource.root()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero.xcodeproj/project.pbxproj")
        let project = try String(contentsOf: projectURL, encoding: .utf8)
        XCTAssertFalse(
            project.contains("com.tubb.fichero.item"),
            "the stale com.tubb.fichero.item declaration is back in project.pbxproj"
        )
        XCTAssertTrue(
            project.contains(UTType.ficheroDragItem.identifier),
            "the generated-plist targets (iOS) lost the drag-item declaration in project.pbxproj"
        )
    }
}
