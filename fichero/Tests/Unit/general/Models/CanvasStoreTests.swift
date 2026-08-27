//
//  CanvasStoreTests.swift
//  FicheroTests
//
//  Unit tests for the per-library, scope-keyed canvas stores (#3082). Covers the
//  pieces exercisable without a live backend: the change-domain registration,
//  the two-scope isolation that stops two windows on different folders from
//  clobbering each other's rows, in-place identity stability, and the coarse
//  (debounced-reload) change-event apply.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// MARK: - Helpers

@MainActor
private func makeLayoutStore() -> CanvasLayoutStore {
    CanvasLayoutStore(client: FicheroClient(libraryPath: "/tmp/test.fichero"))
}

@MainActor
private func makeItemStore() -> CanvasItemStore {
    CanvasItemStore(client: FicheroClient(libraryPath: "/tmp/test.fichero"))
}

private func makeEvent(type: String) throws -> ChangeEvent {
    let payload: [String: Any] = ["type": type, "actor": "test"]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try JSONDecoder().decode(ChangeEvent.self, from: data)
}

/// Build a `CanvasItemDisplay` for seeding (the model has only a decoding init).
private func makeItem(id: String, folderId: String, text: String = "") throws -> CanvasItemDisplay {
    let payload: [String: Any] = ["id": id, "folderId": folderId, "kind": "note", "text": text]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try JSONDecoder().decode(CanvasItemDisplay.self, from: data)
}

// MARK: - CanvasLayoutStore

@MainActor
struct CanvasLayoutStoreTests {

    @Test("changeDomains is exactly [canvas]")
    func changeDomainIsCanvas() {
        let store = makeLayoutStore()
        #expect(store.changeDomains == ["canvas"])
    }

    /// Two windows on different folders must not clobber each other's layout —
    /// the core #3082 fix. Seeding one scope leaves the other untouched, and
    /// `layout(for:)` returns each scope's own rows.
    @Test("layouts are isolated per scope")
    func layoutsAreIsolatedPerScope() {
        let store = makeLayoutStore()
        store.layouts["A"] = [CanvasItemLayout(itemId: "a1", x: 1, y: 1)]
        store.layouts["B"] = [CanvasItemLayout(itemId: "b1", x: 2, y: 2)]

        #expect(store.layout(for: "A").map(\.itemId) == ["a1"])
        #expect(store.layout(for: "B").map(\.itemId) == ["b1"])

        // Mutating scope B leaves A intact.
        store.layouts["B"] = [CanvasItemLayout(itemId: "b1", x: 9, y: 9)]
        #expect(store.layout(for: "A").first?.x == 1)
        #expect(store.layout(for: "B").first?.x == 9)
    }

    @Test("layout(for:) of an unloaded scope is empty")
    func unloadedScopeIsEmpty() {
        let store = makeLayoutStore()
        #expect(store.layout(for: "never-loaded").isEmpty)
    }

    /// Patching one row in place keeps the other rows' identity/values stable —
    /// the no-wholesale-re-render guarantee at the data layer.
    @Test("in-place row patch leaves sibling rows stable")
    func inPlacePatchLeavesSiblingsStable() {
        let store = makeLayoutStore()
        let untouched = CanvasItemLayout(itemId: "keep", x: 5, y: 5)
        store.layouts["A"] = [untouched, CanvasItemLayout(itemId: "move", x: 0, y: 0)]

        if let index = store.layouts["A"]?.firstIndex(where: { $0.itemId == "move" }) {
            store.layouts["A"]?[index].x = 42
        }

        #expect(store.layout(for: "A").first { $0.itemId == "keep" } == untouched)
        #expect(store.layout(for: "A").first { $0.itemId == "move" }?.x == 42)
    }

    /// A `canvas.*` event does not mutate scope rows synchronously — the apply is
    /// a debounced reload (the event carries no scope/item ids yet, #3078).
    @Test("apply does not synchronously clobber loaded scopes")
    func applyDoesNotSynchronouslyMutate() throws {
        let store = makeLayoutStore()
        store.layouts["A"] = [CanvasItemLayout(itemId: "a1", x: 1, y: 1)]
        store.apply(try makeEvent(type: "canvas.layout.saved"))
        #expect(store.layout(for: "A").map(\.itemId) == ["a1"])
    }

    /// `reload()` with no loaded scopes touches no network and completes.
    @Test("reload with no loaded scopes is a no-op")
    func reloadNoScopesIsNoOp() async {
        let store = makeLayoutStore()
        await store.reload()
        #expect(store.layouts.isEmpty)
    }
}

// MARK: - CanvasItemStore

@MainActor
struct CanvasItemStoreTests {

    @Test("changeDomains is exactly [canvas]")
    func changeDomainIsCanvas() {
        let store = makeItemStore()
        #expect(store.changeDomains == ["canvas"])
    }

    @Test("items are isolated per scope")
    func itemsAreIsolatedPerScope() throws {
        let store = makeItemStore()
        store.itemsByScope["A"] = [try makeItem(id: "a1", folderId: "A")]
        store.itemsByScope["B"] = [try makeItem(id: "b1", folderId: "B")]

        #expect(store.items(for: "A").map(\.id) == ["a1"])
        #expect(store.items(for: "B").map(\.id) == ["b1"])

        store.itemsByScope["B"] = []
        #expect(store.items(for: "A").map(\.id) == ["a1"])
        #expect(store.items(for: "B").isEmpty)
    }

    @Test("items(for:) of an unloaded scope is empty")
    func unloadedScopeIsEmpty() {
        let store = makeItemStore()
        #expect(store.items(for: "never-loaded").isEmpty)
    }

    @Test("apply does not synchronously clobber loaded scopes")
    func applyDoesNotSynchronouslyMutate() throws {
        let store = makeItemStore()
        store.itemsByScope["A"] = [try makeItem(id: "a1", folderId: "A")]
        store.apply(try makeEvent(type: "canvas.item.created"))
        #expect(store.items(for: "A").map(\.id) == ["a1"])
    }
}
