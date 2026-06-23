@testable import Fichero
import Foundation
import Testing

struct SidebarDropCleanupTests {

    @Test("sidebar temp drop directories include only fichero-drop parents")
    func collectsOnlyTemporaryDropDirectories() {
        let tempA = URL(fileURLWithPath: "/tmp/fichero-drop-a/file-1.pdf")
        let tempB = URL(fileURLWithPath: "/tmp/fichero-drop-b/file-2.pdf")
        let stable = URL(fileURLWithPath: "/Users/test/Documents/file-3.pdf")

        let result = sidebarTemporaryDropDirectories(for: [tempA, tempB, stable])

        #expect(Set(result) == Set([tempA.deletingLastPathComponent(), tempB.deletingLastPathComponent()]))
    }

    @Test("sidebar temp drop directories dedupe siblings in one temp folder")
    func dedupesDirectories() {
        let urlOne = URL(fileURLWithPath: "/tmp/fichero-drop-a/file-1.pdf")
        let urlTwo = URL(fileURLWithPath: "/tmp/fichero-drop-a/file-2.pdf")

        let result = sidebarTemporaryDropDirectories(for: [urlOne, urlTwo])

        #expect(result == [urlOne.deletingLastPathComponent()])
    }
}
