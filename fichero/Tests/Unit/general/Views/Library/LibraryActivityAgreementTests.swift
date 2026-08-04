@testable import Fichero
import XCTest

/// The library and the sidebar must say the same thing about the same document
/// (#4417).
///
/// #4417 was fixed in the sidebar and only there. `ContainerActivity` decided
/// that a container is not the subject of its children's work, so a folder
/// stopped borrowing their spinner and started showing "Processing contents —
/// 3 of 4 done". The library list and table kept rendering on
/// `document.status == .processing` alone.
///
/// So one folder, one moment, two panes, two different claims — and the
/// library's was the false one, which is precisely the claim the issue exists
/// to remove. That is the sidebar-versus-library disagreement class: not a
/// missed instance, but a fix that reached whichever surface was being looked
/// at.
///
/// These pin the RULE rather than either pane's current rendering, because the
/// defect was never "the library draws the wrong glyph" — it was that two
/// surfaces answered the same question independently.
final class LibraryActivityAgreementTests: XCTestCase {

    // MARK: - The rule both panes now ask

    /// The defect, stated directly: a container with busy children is NOT
    /// itself processing, whatever its own status record says.
    func testAContainerWithBusyChildrenDoesNotShowTheLeafSpinner() throws {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: true,
            busyChildren: 1,
            totalChildren: 4
        )

        XCTAssertFalse(
            activity.showsLeafSpinner,
            "busy children must win over own-status; that is the whole issue"
        )
        // `progress` is Double? — nil means "no determinate fraction to show".
        // Unwrapping here asserts BOTH that a fraction exists and that it is
        // right; XCTAssertEqual against an optional silently accepted nil.
        let progress = try XCTUnwrap(activity.progress)
        XCTAssertEqual(progress, 0.75, accuracy: 0.001)
    }

    /// And a genuine leaf keeps its spinner — the fix must not be "never spin",
    /// which is how a narrowing fix usually goes wrong.
    func testARealLeafStillShowsItsSpinner() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: true,
            busyChildren: 0,
            totalChildren: 0
        )

        XCTAssertTrue(activity.showsLeafSpinner)
        XCTAssertNil(activity.progress, "a leaf has no children to be determinate about")
    }

    /// The folder-level catalogue stage: the container really is the subject,
    /// with children present but idle. It must still read as its own work.
    func testAContainerProcessingWithIdleChildrenIsItsOwnSubject() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: true,
            busyChildren: 0,
            totalChildren: 6
        )

        XCTAssertTrue(activity.showsLeafSpinner)
    }

    // MARK: - Neither pane may re-derive it

    /// The property that actually stops the drift. The library rendered on a
    /// raw status check for as long as it did because nothing said it could
    /// not; the sidebar's fix was invisible from the library's side.
    func testTheLibraryDoesNotReadStatusDirectlyForItsIndicator() throws {
        let source = Self.code(of: try AppSource.text("Views/Library/LibraryViewComponents.swift"))

        XCTAssertFalse(
            source.contains("if document.status == .processing"),
            """
            the library is deciding activity from a leaf's own status again — \
            that is the #4417 claim the sidebar stopped making, reintroduced in \
            the other pane. Route through LibraryActivityIndicator.
            """
        )
        XCTAssertTrue(source.contains("LibraryActivityIndicator"))
    }

    /// Both panes reach the rule through the same resolver, so a change to the
    /// rule cannot land in one surface only — which is how this happened.
    func testBothPanesResolveThroughContainerActivity() throws {
        for path in [
            "Views/Library/LibraryActivityIndicator.swift",
            "Views/Sidebar/ItemRow/SidebarItemRow.swift"
        ] {
            let source = Self.code(of: try AppSource.text(path))
            XCTAssertTrue(
                source.contains("ContainerActivity.resolve("),
                "\(path) must ask the shared resolver, not decide for itself"
            )
        }
    }

    // MARK: - Support

    /// Source with `//` comments removed — the comments above and in the files
    /// under test both quote the very strings these assertions forbid.
    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }
}
