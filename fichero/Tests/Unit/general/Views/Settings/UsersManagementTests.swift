@testable import Fichero
import XCTest

/// #3787 — Settings user management. Locks the roles the Share sheet may grant and
/// the Users pane's state resolution. Owner is a whole-library administrator granted
/// deliberately in Settings → People, never handed out casually while sharing.
final class UsersManagementTests: XCTestCase {

    // MARK: - Share sheet roles (#3787)

    func testShareSheetOffersViewerAndEditorOnlyNotOwner() {
        XCTAssertEqual(ShareLibrarySheet.shareRoles, ["editor", "viewer"])
        XCTAssertFalse(
            ShareLibrarySheet.shareRoles.contains("owner"),
            "Owner is granted deliberately in Settings → People, not from the share sheet"
        )
    }

    func testShareSheetDefaultRoleIsOneItOffers() {
        // The default assignment must be a role the sheet actually offers, or the
        // Picker selection would bind to a tag with no matching row.
        XCTAssertTrue(ShareLibrarySheet.shareRoles.contains("viewer"))
    }

    // MARK: - Users pane presentation (#3787)

    private func input(
        isLoading: Bool = false,
        loadError: String? = nil,
        usersEmpty: Bool = true,
        hasCurrentUser: Bool = false,
        hasAuthzSnapshot: Bool = false,
        listAccessDenied: Bool = false,
        isOwnerAccess: Bool = false
    ) -> UsersSettingsPresentation.Input {
        .init(
            isLoading: isLoading,
            loadError: loadError,
            usersEmpty: usersEmpty,
            hasCurrentUser: hasCurrentUser,
            hasAuthzSnapshot: hasAuthzSnapshot,
            listAccessDenied: listAccessDenied,
            isOwnerAccess: isOwnerAccess
        )
    }

    func testPresentationLoadingWhenNothingLoadedYet() {
        XCTAssertEqual(UsersSettingsPresentation.resolve(input(isLoading: true)), .loading)
    }

    /// A load failure with nothing loaded must surface honestly, never a blank pane.
    func testPresentationLoadErrorSurfaces() {
        XCTAssertEqual(
            UsersSettingsPresentation.resolve(input(loadError: "boom")),
            .loadError("boom")
        )
    }

    func testPresentationEmptyWhenNothingAndNoError() {
        XCTAssertEqual(UsersSettingsPresentation.resolve(input()), .empty)
    }

    func testPresentationAccountDetailsOnceSomethingLoaded() {
        XCTAssertEqual(
            UsersSettingsPresentation.resolve(input(usersEmpty: false, hasCurrentUser: true)),
            .accountDetails
        )
    }

    /// Still loading, but the signed-in user is already known → show details, not a
    /// spinner that would hide the pane the owner is trying to use.
    func testPresentationYieldsToDataWhileStillLoading() {
        XCTAssertEqual(
            UsersSettingsPresentation.resolve(input(isLoading: true, hasCurrentUser: true)),
            .accountDetails
        )
    }
}
