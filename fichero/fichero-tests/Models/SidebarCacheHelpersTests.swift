@testable import Fichero
import Foundation
import Testing

struct SidebarCacheHelpersTests {
    private let libraryIdA = UUID()
    private let libraryIdB = UUID()

    private func libraryHeader(id: UUID, name: String) -> SidebarItem {
        SidebarItem(
            id: "library:\(id.uuidString)",
            name: name,
            icon: "book.closed",
            category: .library,
            itemType: .libraryHeader,
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: id,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    @Test("replacing a library header patches only that library")
    func replaceExistingHeaderInPlace() {
        let first = libraryHeader(id: libraryIdA, name: "Alpha")
        let second = libraryHeader(id: libraryIdB, name: "Beta")
        let updatedSecond = libraryHeader(id: libraryIdB, name: "Beta Updated")

        let result = sidebarReplacingLibraryHeader([first, second], with: updatedSecond)

        #expect(result.map(\.name) == ["Alpha", "Beta Updated"])
        #expect(result.map(\.id) == [first.id, second.id])
    }

    @Test("replacing a missing library header appends it")
    func appendMissingHeader() {
        let first = libraryHeader(id: libraryIdA, name: "Alpha")
        let second = libraryHeader(id: libraryIdB, name: "Beta")

        let result = sidebarReplacingLibraryHeader([first], with: second)

        #expect(result.map(\.name) == ["Alpha", "Beta"])
    }
}
