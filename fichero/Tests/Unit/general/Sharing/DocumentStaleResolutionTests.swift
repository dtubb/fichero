import Foundation
import Testing

@testable import Fichero

/// #5348, the document half: a text save sends the version the editor saw; after the engine refuses it as stale the next
/// save is the person's choice to replace the other Mac's text, so it sends none.
@MainActor
struct DocumentStaleResolutionTests {
    @Test func firstSaveSendsTheEditorsCopyThenTheVersionTheLastSaveSaw() {
        let store = DocumentStore(apiClient: APIClient())
        let opened = Date(timeIntervalSince1970: 100)
        #expect(store.versionForNextTextSave("d", seen: opened) == opened)
        let saved = Date(timeIntervalSince1970: 200)
        store.pageContentVersions["d"] = saved
        #expect(store.versionForNextTextSave("d", seen: opened) == saved)
    }

    @Test func afterARefusalTheNextSaveSendsNoVersionAndThenTheOneAfterIsGuardedAgain() {
        let store = DocumentStore(apiClient: APIClient())
        let opened = Date(timeIntervalSince1970: 100)
        store.textSaveWasRefused("d")
        #expect(store.versionForNextTextSave("d", seen: opened) == nil)
        store.pageContentVersions["d"] = Date(timeIntervalSince1970: 300)
        #expect(store.versionForNextTextSave("d", seen: opened) == Date(timeIntervalSince1970: 300))
    }

    @Test func aRefusalForOneDocumentDoesNotUnguardAnother() {
        let store = DocumentStore(apiClient: APIClient())
        let opened = Date(timeIntervalSince1970: 100)
        store.textSaveWasRefused("a")
        #expect(store.versionForNextTextSave("b", seen: opened) == opened)
    }
}
