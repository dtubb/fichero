//
//  ModelComparisonStoreTests.swift
//  FicheroTests
//
//  Unit tests for ModelComparisonStore (#1863 — observable data layer).
//  Verifies the store wraps ModelComparisonService as its single transport and
//  forwards the observable comparison state, so the two comparison views never
//  touch the endpoint directly.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ModelComparisonStoreTests {

    /// A freshly constructed store forwards the transport's empty initial state.
    /// This is the pure, offline-safe wiring check: the store builds without a
    /// backend and exposes the service's published properties read-through.
    @Test("Fresh store forwards the transport's empty state")
    func freshStoreForwardsEmptyState() {
        let store = ModelComparisonStore()

        #expect(store.isComparing == false)
        #expect(store.lastResult == nil)
        #expect(store.history.isEmpty)
        #expect(store.presets.isEmpty)
        #expect(store.availableModels.isEmpty)
        #expect(store.error == nil)
    }

    /// The store shares the injected service instance — confirming the store is a
    /// thin accessor over one transport rather than spinning up its own hidden
    /// endpoint client.
    @Test("Store uses the injected service as its transport")
    func storeUsesInjectedService() {
        let service = ModelComparisonService()
        let store = ModelComparisonStore(service: service)

        #expect(store.service === service)
    }

    /// `selectResult` is a no-op when the id is nil or absent from history, so a
    /// stray selection can never crash or fabricate a `lastResult`.
    @Test("selectResult ignores nil and unknown ids")
    func selectResultIgnoresUnknownIds() {
        let store = ModelComparisonStore()

        store.selectResult(id: nil)
        #expect(store.lastResult == nil)

        store.selectResult(id: "does-not-exist")
        #expect(store.lastResult == nil)
    }
}
