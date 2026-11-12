@testable import Fichero
import Foundation
import Testing

/// The window does not watch the document store itself (`read.a-click-shows-its-folder-at-once`,
/// #4228): an `.onChange(of: documentStore…)` on `ContentView` re-evaluated the whole window on
/// every folder load and change-stream splice. `DocumentStoreChangeObserver` watches instead.
struct ContentViewStoreObserverTests {

    private func source(_ path: String) throws -> String {
        let repoRoot = try AppSource.root().deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: repoRoot.appendingPathComponent(path), encoding: .utf8)
    }

    @Test("ContentView's layout has no onChange on the document store, and hosts the observer")
    func windowDoesNotWatchTheStore() throws {
        let root = try source("fichero/fichero/Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(!root.contains(".onChange(of: documentStore."))
        #expect(root.contains("DocumentStoreChangeObserver("))
    }

    @Test("the observer watches the three store values the window used to")
    func observerWatchesTheSameValues() throws {
        let observer = try source("fichero/fichero/Views/Shell/ContentView/DocumentStoreChangeObserver.swift")
        for value in ["store.collections", "store.currentDocuments", "store.revision"] {
            #expect(observer.contains(".onChange(of: \(value))"))
        }
    }
}
