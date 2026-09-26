@testable import Fichero
import XCTest

/// `AppSource` must find the root from anywhere, and say so loudly when it
/// cannot (#4493).
///
/// The helper it replaces failed by returning a wrong-but-plausible URL, so
/// the error surfaced later as a file-not-found inside an unrelated assertion.
/// Three tests died that way tonight and the message named a path nobody
/// recognised. So the thing under test here is not "can it read a file" — it
/// is "does it distinguish a moved ROOT from a missing FILE, and does it say
/// which".
final class AppSourceTests: XCTestCase {

    // MARK: - It resolves, and does so without counting

    func testItFindsTheAppSourceRoot() throws {
        let root = try AppSource.root()

        XCTAssertEqual(root.lastPathComponent, "fichero")
        XCTAssertTrue(
            FileManager.default.fileExists(atPath: root.appendingPathComponent("Models").path)
        )
    }

    /// The property that makes this immune to the bug it replaces: the answer
    /// does not depend on how deep the CALLER sits. Two files at different
    /// nesting levels must agree — a hardcoded depth cannot manage that, which
    /// is why there were ten different depths in the suite.
    func testTheRootIsTheSameFromDifferentNestingDepths() throws {
        let fromHere = try AppSource.root()
        let fromDeeper = try AppSource.root(
            from: "\(#filePath)/Views/Library/ViewModes/Columns/Deeply/Nested.swift"
        )

        XCTAssertEqual(fromHere.path, fromDeeper.path)
    }

    func testItReadsAFileThroughTheRoot() throws {
        let source = try AppSource.text("Models/DocumentStore.swift")

        XCTAssertTrue(source.contains("final class DocumentStore"))
    }

    // MARK: - The floor

    /// **The fixture that proves it fires.** A root that exists and holds
    /// nothing must produce the legible failure, not a read error later.
    func testAMissingRootIsALegibleFailureNotAReadError() throws {
        let empty = FileManager.default.temporaryDirectory
            .appendingPathComponent("appsource-floor-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: empty, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: empty) }

        // A path that exists but has no `fichero/Models` above it anywhere.
        // `/var/folders/...` has no app target in any ancestor.
        do {
            _ = try AppSource.root(from: "/private/tmp/not-the-app/Test.swift")
            XCTFail("a root that cannot be found must throw, not return a plausible URL")
        } catch let error as AppSource.NotFound {
            XCTAssertTrue(error.description.contains("BLIND"))
            XCTAssertTrue(
                error.description.contains("/private/tmp/not-the-app"),
                "the failure must name the path it started from"
            )
            XCTAssertTrue(
                error.description.contains("fichero/Models"),
                "and what it was looking for"
            )
        }
    }

    /// A missing FILE under a good root is a different failure from a missing
    /// ROOT, and must stay different. Conflating them is how the old helpers
    /// made a moved tree look like a deleted file.
    func testAMissingFileUnderAGoodRootIsNotTheRootError() throws {
        do {
            _ = try AppSource.text("Models/ThisFileDoesNotExist.swift")
            XCTFail("expected a read error")
        } catch is AppSource.NotFound {
            XCTFail("a missing FILE must not be reported as a missing ROOT")
        } catch {
            // The underlying read error — correct.
        }
    }

    /// The tree walk sees real files. A guard built on it asserts over whatever
    /// this returns, so an empty or tiny result would make every such guard pass
    /// while checking nothing.
    func testItWalksASubtreeAndReturnsRelativePathsWithCommentsStripped() throws {
        let views = try AppSource.swiftFiles(under: "Views")
        XCTAssertGreaterThan(views.count, 100, "the app has far more than 100 view files")
        XCTAssertTrue(
            views.allSatisfy { $0.path.hasPrefix("Views/") && $0.path.hasSuffix(".swift") },
            "paths come back relative to the app root, not absolute"
        )
        XCTAssertFalse(
            views.contains { $0.code.contains("\n//") },
            "comment lines are stripped, so a guard cannot fail on a file's own explanation"
        )
    }

    /// A subtree that is not there is BLIND, and says so as itself — not as
    /// `NotFound`, which would send the reader hunting for a moved test tree, and
    /// not as an empty array, which every caller would read as "nothing offends".
    func testAMissingSubtreeIsBlindRatherThanAnEmptyResult() throws {
        do {
            let found = try AppSource.swiftFiles(under: "ThisDirectoryDoesNotExist")
            XCTFail("expected BLIND, got \(found.count) files")
        } catch is AppSource.NotFound {
            XCTFail("a missing SUBTREE must not be reported as a missing ROOT")
        } catch let error as AppSource.CannotWalk {
            XCTAssertTrue(error.description.contains("BLIND"), "and it names itself blind")
        }
    }
}
