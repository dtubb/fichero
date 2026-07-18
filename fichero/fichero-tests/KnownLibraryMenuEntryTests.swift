@testable import Fichero
import Testing

@Suite("KnownLibraryMenuEntry")
struct KnownLibraryMenuEntryTests {

    @Test("a non-empty server name is used after trimming whitespace")
    func usesTrimmedName() {
        let entry = KnownLibraryMenuEntry(
            id: "library-1",
            path: "/Users/test/Archive.fichero",
            name: "  Archive  ",
            addedAt: nil,
            lastAccessed: nil
        )

        #expect(entry.displayName == "Archive")
    }

    @Test("missing or blank names fall back to the library package filename")
    func fallsBackToPathName() {
        let missing = KnownLibraryMenuEntry(
            id: "library-1",
            path: "/Users/test/Archive.fichero",
            name: nil,
            addedAt: nil,
            lastAccessed: nil
        )
        let blank = KnownLibraryMenuEntry(
            id: "library-2",
            path: "/Users/test/Notes.fichero",
            name: " \n ",
            addedAt: nil,
            lastAccessed: nil
        )

        #expect(missing.displayName == "Archive")
        #expect(blank.displayName == "Notes")
    }
}
