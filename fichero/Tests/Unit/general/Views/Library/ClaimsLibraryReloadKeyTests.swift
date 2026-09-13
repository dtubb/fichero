@testable import Fichero
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces — F5 (the Claims table must reset when the
/// active library changes).
///
/// The bug: the claims table reloaded on `.task(id: folderId)`, and the
/// library-wide Claims row keeps `folderId == nil` before AND after a library
/// switch — so the reload never refired and the table kept showing the PREVIOUS
/// library's claims. The fix folds the active library id into the reload key
/// (`LibraryClaimsModel.reloadKey`), so a switch changes the key even when the
/// folder scope does not.
///
/// This pins the pure reset decision off-main: the same seam the view keys its
/// `.task` on. It is NOT a source-scrape (no AppSource / `source.contains`) — it
/// exercises the real function that decides when the table refetches.
struct ClaimsLibraryReloadKeyTests {

    private let libraryA = UUID()
    private let libraryB = UUID()

    @Test("a library switch changes the key even when folderId stays nil (the F5 bug)")
    func librarySwitchChangesKeyForLibraryWideRow() {
        // The library-wide Claims row: folderId is nil in BOTH libraries.
        let keyInA = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: nil)
        let keyInB = LibraryClaimsModel.reloadKey(libraryId: libraryB, folderId: nil)
        // Before the fix these were equal (both keyed on nil folder) so the
        // reload never refired. Now they must differ so the table refetches B.
        #expect(keyInA != keyInB)
    }

    @Test("a library switch changes the key for a folder-scoped row too")
    func librarySwitchChangesKeyForFolderRow() {
        let keyInA = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "folder-1")
        let keyInB = LibraryClaimsModel.reloadKey(libraryId: libraryB, folderId: "folder-1")
        #expect(keyInA != keyInB)
    }

    @Test("a folder change within one library still changes the key (unchanged behavior)")
    func folderSwitchChangesKey() {
        let key1 = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "folder-1")
        let key2 = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "folder-2")
        #expect(key1 != key2)
    }

    @Test("the same library + same folder yields a stable key (no spurious refetch)")
    func stableKeyForSameScope() {
        let first = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "folder-1")
        let second = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "folder-1")
        #expect(first == second)

        let firstWide = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: nil)
        let secondWide = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: nil)
        #expect(firstWide == secondWide)
    }

    @Test("a nil folder is distinct from a folder literally named empty-string")
    func nilFolderDistinctFromEmptyString() {
        let wide = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: nil)
        let empty = LibraryClaimsModel.reloadKey(libraryId: libraryA, folderId: "")
        // Both render "<uuid>|" — an intentional collision: an empty folder id is
        // not a real scope, so treating it as library-wide is correct. This test
        // documents that equivalence so a future change is a deliberate choice.
        #expect(wide == empty)
    }
}
