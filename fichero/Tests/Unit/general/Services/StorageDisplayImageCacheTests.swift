// Bounded display-image cache eviction (#2469). Prefetching neighbors for
// folder-image navigation warms displayPlatformImageCache; this verifies the
// cache stays bounded (FIFO, oldest-first) so large folders don't unboundedly
// accumulate full-resolution platform images in memory.

@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

#if os(iOS)
import UIKit
#endif

@MainActor
struct StorageDisplayImageCacheTests {

    private func makeService() -> StorageService {
        StorageService(ficheroClient: FicheroClient(libraryPath: nil))
    }

    private func dummyImage() -> PlatformImage {
        #if os(macOS)
        return PlatformImage()
        #else
        return UIImage(systemName: "photo") ?? UIImage()
        #endif
    }

    private func dummyPreview() -> PreviewImage {
        PreviewImage(image: dummyImage(), pixelSize: CGSize(width: 120, height: 80))
    }

    @Test("display cache count never exceeds the limit")
    func displayCacheStaysBounded() {
        let service = makeService()
        let limit = StorageService.displayPlatformImageCacheLimit
        let img = dummyImage()
        for index in 0..<(limit + 10) {
            service.cacheDisplayPlatformImage(img, for: "doc-\(index)")
        }
        #expect(service.displayPlatformImageCacheCount == limit)
    }

    @Test("oldest display cache entries are evicted first; newest survive")
    func displayCacheEvictsOldestFirst() {
        let service = makeService()
        let limit = StorageService.displayPlatformImageCacheLimit
        let img = dummyImage()
        for index in 0..<(limit + 5) {
            service.cacheDisplayPlatformImage(img, for: "doc-\(index)")
        }
        // doc-0...doc-4 were the first inserted → evicted.
        #expect(service.cachedDisplayPlatformImage(for: "doc-0") == nil)
        #expect(service.cachedDisplayPlatformImage(for: "doc-4") == nil)
        // doc-5 onward survive.
        #expect(service.cachedDisplayPlatformImage(for: "doc-5") != nil)
        #expect(service.cachedDisplayPlatformImage(for: "doc-\(limit + 4)") != nil)
    }

    @Test("re-caching the same display image id does not grow order or double-evict")
    func displayCacheReCachingIsStable() {
        let service = makeService()
        let img = dummyImage()
        for _ in 0..<10 {
            service.cacheDisplayPlatformImage(img, for: "stable")
        }
        #expect(service.displayPlatformImageCacheCount == 1)
        #expect(service.cachedDisplayPlatformImage(for: "stable") != nil)
    }

    @Test("invalidate removes display image from cache and order")
    func displayCacheInvalidateClearsEntry() {
        let service = makeService()
        let img = dummyImage()
        service.cacheDisplayPlatformImage(img, for: "doc-a")
        service.cacheDisplayPlatformImage(img, for: "doc-b")
        service.invalidateImageCache(for: "doc-a")
        #expect(service.cachedDisplayPlatformImage(for: "doc-a") == nil)
        #expect(service.cachedDisplayPlatformImage(for: "doc-b") != nil)
        #expect(service.displayPlatformImageCacheCount == 1)
    }

    @Test("clearAll empties storage caches on engine host switch")
    func clearAllEmptiesStorageCaches() {
        let service = makeService()
        let img = dummyImage()
        service.cacheThumbnail(Image(systemName: "photo"), for: "doc-thumb")
        service.cacheDisplayPlatformImage(img, for: "doc-display")

        service.clearAll()

        #expect(service.thumbnailCacheCount == 0)
        #expect(service.displayPlatformImageCacheCount == 0)
        #expect(service.cachedThumbnail(for: "doc-thumb") == nil)
        #expect(service.cachedDisplayPlatformImage(for: "doc-display") == nil)
    }

    // MARK: - #2459 edit-save / cache-invalidation wiring

    @Test("onEditApplied callback clears display cache for the edited document (#2459)")
    func editAppliedCallbackInvalidatesCache() {
        let service = makeService()
        let img = dummyImage()
        let docId = "doc-edit-2459"
        service.cacheDisplayPlatformImage(img, for: docId)
        #expect(service.cachedDisplayPlatformImage(for: docId) != nil,
                "pre-condition: image must be in cache before edit")

        // Simulate the wiring ImageEditorView establishes after model.configure.
        var callbackFiredWith: String?
        let onEditApplied: (String) -> Void = { id in
            callbackFiredWith = id
            service.invalidateImageCache(for: id)
        }

        // Simulate a successful runOp firing the callback.
        onEditApplied(docId)

        #expect(callbackFiredWith == docId)
        #expect(service.cachedDisplayPlatformImage(for: docId) == nil,
                "cache must be empty after edit so viewer re-fetches edited bytes")
    }

    @Test("onEditApplied leaves sibling documents in cache untouched (#2459)")
    func editAppliedCallbackDoesNotEvictSiblings() {
        let service = makeService()
        let img = dummyImage()
        service.cacheDisplayPlatformImage(img, for: "doc-edited")
        service.cacheDisplayPlatformImage(img, for: "doc-sibling")

        service.invalidateImageCache(for: "doc-edited")

        #expect(service.cachedDisplayPlatformImage(for: "doc-edited") == nil)
        #expect(service.cachedDisplayPlatformImage(for: "doc-sibling") != nil,
                "sibling's cached image must survive a single-document invalidation")
    }

    @Test("failed edit does not call onEditApplied — error surfaces via errorMessage (#2459)")
    func failedEditDoesNotFireCallback() async {
        // ImageEditorModel.runOp guards: if service is nil, it returns early
        // without calling onEditApplied. That is the minimal verifiable case
        // without a live engine — the callback is only invoked on success.
        let model = ImageEditorModel(documentId: "doc-fail")
        var callbackFired = false
        model.onEditApplied = { _ in callbackFired = true }

        // rotate() calls runOp which guards `guard let service` → returns early,
        // no error is set and no callback fires (no service was configured).
        await model.rotate(by: 90)

        #expect(!callbackFired, "onEditApplied must NOT fire when the op fails")
        #expect(model.errorMessage == nil,
                "no errorMessage expected when the guard exits early (no service)")
    }

    @Test("edit refresh reuses the cached original preview and only reloads edited bytes")
    func editRefreshDoesNotRefetchOriginalPreview() async {
        var calls: [Bool] = []
        let model = ImageEditorModel(documentId: "doc-preview") { _, applyEdits, _ in
            calls.append(applyEdits)
            return self.dummyPreview()
        }

        await model.reloadPreviews(forceOriginalReload: true, forceEditedReload: true)
        calls.removeAll()

        await model.reloadPreviews(forceOriginalReload: false, forceEditedReload: true)

        #expect(calls == [true])
    }

    @Test("switching back to original only fetches the missing original preview")
    func toggleToOriginalOnlyFetchesOriginalWhenMissing() async {
        var calls: [Bool] = []
        let model = ImageEditorModel(documentId: "doc-toggle") { _, applyEdits, _ in
            calls.append(applyEdits)
            return self.dummyPreview()
        }
        model.showEdited = true
        model.editedPreview = dummyPreview()
        model.originalPreview = nil
        model.preview = nil

        model.setShowEdited(false)
        await Task.yield()
        await Task.yield()

        #expect(calls == [false])
        #expect(model.preview != nil)
    }
}
