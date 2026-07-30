@testable import Fichero
import XCTest

/// Policy tests for the two shell-toolbar controls added by #4288 (library-pane
/// toggle) and #4289 (Finder-style sort + filter). The buttons themselves are
/// thin renderers over these models, so the behaviour that can regress —
/// symbol/help/enablement, and the single sort path — is asserted here rather
/// than on pixels.
@MainActor
final class LibraryToolbarPolicyTests: XCTestCase {

    // MARK: - #4288 library pane toggle

    private func visibility(grid: Bool, canvas: Bool, reading: Bool) -> PaneVisibility {
        PaneVisibility(grid: grid, canvas: canvas, reading: reading)
    }

    func testToggleReportsVisibleWhenGridPaneIsShown() {
        let model = LibraryPaneToggleModel(
            paneVisibility: visibility(grid: true, canvas: true, reading: false)
        )

        XCTAssertTrue(model.isVisible)
        XCTAssertEqual(model.systemImage, "rectangle.leadinghalf.inset.filled")
        XCTAssertFalse(model.nextVisibility, "a visible pane toggles to hidden")
        XCTAssertTrue(model.help.contains("Hide"))
    }

    func testToggleReportsHiddenWhenGridPaneIsCollapsed() {
        let model = LibraryPaneToggleModel(
            paneVisibility: visibility(grid: false, canvas: false, reading: true)
        )

        XCTAssertFalse(model.isVisible)
        XCTAssertEqual(model.systemImage, "rectangle")
        XCTAssertTrue(model.nextVisibility, "a hidden pane toggles to visible")
        XCTAssertTrue(model.isEnabled, "showing a pane is always allowed")
        XCTAssertTrue(model.help.contains("Show"))
    }

    /// The ≥1-visible-pane invariant (#1696) refuses to hide the last pane, so
    /// the button must be disabled rather than silently doing nothing.
    func testToggleIsDisabledWhenTheLibraryPaneIsTheOnlyVisiblePane() {
        let model = LibraryPaneToggleModel(
            paneVisibility: visibility(grid: true, canvas: false, reading: false)
        )

        XCTAssertTrue(model.isVisible)
        XCTAssertFalse(model.canHide)
        XCTAssertFalse(model.isEnabled)
        XCTAssertFalse(model.help.contains("Hide"), "help explains why, not a lie about hiding")
    }

    func testToggleIsEnabledWhenAnotherPaneWouldSurvive() {
        for other in [(true, false), (false, true), (true, true)] {
            let model = LibraryPaneToggleModel(
                paneVisibility: visibility(grid: true, canvas: other.0, reading: other.1)
            )
            XCTAssertTrue(model.isEnabled, "canvas=\(other.0) reading=\(other.1)")
        }
    }

    /// The keyboard equivalent is the existing View-menu command; the button
    /// advertises it rather than registering a duplicate shortcut.
    func testToggleHelpAdvertisesTheExistingPaneShortcut() {
        let shown = LibraryPaneToggleModel(
            paneVisibility: visibility(grid: true, canvas: true, reading: false)
        )
        let hidden = LibraryPaneToggleModel(
            paneVisibility: visibility(grid: false, canvas: true, reading: false)
        )

        XCTAssertTrue(shown.help.contains(LibraryPaneToggleModel.shortcutHint))
        XCTAssertTrue(hidden.help.contains(LibraryPaneToggleModel.shortcutHint))
    }

    /// Applying `nextVisibility` through the same invariant that produced the
    /// model actually flips the pane — the model and the mutation agree.
    func testNextVisibilityAppliedThroughTheInvariantFlipsThePane() {
        let start = visibility(grid: true, canvas: true, reading: false)
        let model = LibraryPaneToggleModel(paneVisibility: start)

        let next = start.settingVisible(.grid, model.nextVisibility)
        XCTAssertFalse(next.grid)
        XCTAssertTrue(next.isAnyVisible)

        let back = next.settingVisible(.grid, LibraryPaneToggleModel(paneVisibility: next).nextVisibility)
        XCTAssertTrue(back.grid)
    }

    // MARK: - #4289 sort menu

    func testSortMenuProjectsTheSharedState() {
        let state = LibraryToolbarState()
        state.sortFieldRaw = LibrarySortField.updatedAt.rawValue
        state.sortAscending = false

        let model = state.sortMenuModel
        XCTAssertEqual(model.selectedField, .updatedAt)
        XCTAssertFalse(model.ascending)
        XCTAssertEqual(model.label, LibrarySortField.updatedAt.rawValue)
        XCTAssertEqual(model.directionSystemImage, "arrow.down")
        XCTAssertTrue(model.help.contains("descending"))
    }

    func testSortMenuOffersEveryFieldAndChecksExactlyOne() {
        let state = LibraryToolbarState()
        state.sortFieldRaw = LibrarySortField.fileType.rawValue

        let model = state.sortMenuModel
        XCTAssertEqual(model.fields, LibrarySortField.allCases)
        XCTAssertEqual(model.fields.filter { model.isSelected($0) }, [.fileType])
    }

    /// Picking a field from the toolbar writes the ONE shared sort model — the
    /// same values the View menu, the table headers and the per-folder
    /// persistence read. No second sort path (#4282).
    func testSelectingAFieldWritesTheSharedStateAndKeepsDirection() {
        let state = LibraryToolbarState()
        state.sortAscending = false

        state.apply(state.sortMenuModel.selecting(.createdAt))

        XCTAssertEqual(state.sortFieldRaw, LibrarySortField.createdAt.rawValue)
        XCTAssertEqual(state.sortField, .createdAt)
        XCTAssertFalse(state.sortAscending, "changing field must not silently flip direction")
    }

    func testReselectingTheActiveFieldIsANoOp() {
        let state = LibraryToolbarState()
        state.sortFieldRaw = LibrarySortField.status.rawValue
        state.sortAscending = true

        state.apply(state.sortMenuModel.selecting(.status))

        XCTAssertEqual(state.sortField, .status)
        XCTAssertTrue(state.sortAscending, "re-picking the checked field is not a hidden direction flip")
    }

    func testDirectionIsSetIndependentlyOfField() {
        let state = LibraryToolbarState()
        state.sortFieldRaw = LibrarySortField.name.rawValue

        state.apply(state.sortMenuModel.settingAscending(false))
        XCTAssertFalse(state.sortAscending)
        XCTAssertEqual(state.sortField, .name, "direction change must not move the field")

        state.apply(state.sortMenuModel.settingAscending(true))
        XCTAssertTrue(state.sortAscending)
        XCTAssertEqual(state.sortField, .name)
    }

    /// The comparator the menu selection produces is the one `LibrarySortField`
    /// already publishes — the toolbar does not build its own.
    func testMenuSelectionResolvesToTheSingleComparatorSource() {
        let state = LibraryToolbarState()
        state.apply(state.sortMenuModel.selecting(.createdAt).settingAscending(false))

        let expected = LibrarySortField.createdAt.comparator(ascending: false)
        let actual = state.sortField.comparator(ascending: state.sortAscending)

        XCTAssertEqual(actual.count, expected.count)
        XCTAssertEqual(actual.first?.keyPath, expected.first?.keyPath)
        XCTAssertEqual(actual.first?.order, expected.first?.order)
    }

    /// A field the table has no column for must resolve to a nil column
    /// comparator, so the toolbar can select it without the Table's sortOrder
    /// binding ever carrying an unmappable descriptor (#4282).
    func testToolbarOnlyFieldsHaveNoTableColumnComparator() {
        XCTAssertNil(LibrarySortField.updatedAt.outlineColumnComparator(ascending: true))
        XCTAssertNil(LibrarySortField.fileType.outlineColumnComparator(ascending: true))
        XCTAssertNotNil(LibrarySortField.name.outlineColumnComparator(ascending: true))
    }

    // MARK: - #4289 filter toggle

    func testFilterToggleReflectsAndInvertsTheBarState() {
        let inactive = LibraryFilterToggleModel(isAvailable: true, isActive: false)
        XCTAssertEqual(inactive.systemImage, "line.3.horizontal.decrease.circle")
        XCTAssertTrue(inactive.nextActive)
        XCTAssertTrue(inactive.help.contains("Filter"))

        let active = LibraryFilterToggleModel(isAvailable: true, isActive: true)
        XCTAssertEqual(active.systemImage, "line.3.horizontal.decrease.circle.fill")
        XCTAssertFalse(active.nextActive)
        XCTAssertTrue(active.help.contains("Hide"))
    }

    /// The flag varies the item's CONTENT (the toolbar item itself is declared
    /// unconditionally, per #3163), so "off" has to be representable in the
    /// model rather than by dropping the ToolbarItem.
    func testFilterToggleReportsUnavailableWhenTheFeatureIsOff() {
        let model = LibraryFilterToggleModel(isAvailable: false, isActive: false)
        XCTAssertFalse(model.isAvailable)
    }

    func testSetFilterBarWritesOnlyOnChange() {
        let state = LibraryToolbarState()
        XCTAssertFalse(state.showFilterBar)

        state.setFilterBar(true)
        XCTAssertTrue(state.showFilterBar)

        state.setFilterBar(true)
        XCTAssertTrue(state.showFilterBar)

        state.setFilterBar(false)
        XCTAssertFalse(state.showFilterBar)
    }

    /// Toolbar and ⌘F drive the same flag, so the two affordances can never
    /// disagree about whether the filter bar is up.
    func testToolbarAndKeyboardShareOneFilterFlag() {
        let state = LibraryToolbarState()

        state.showFilterBar = true   // as ⌘F does
        XCTAssertTrue(LibraryFilterToggleModel(isAvailable: true, isActive: state.showFilterBar).isActive)

        state.setFilterBar(false)    // as the toolbar button does
        XCTAssertFalse(state.showFilterBar)
    }
}
