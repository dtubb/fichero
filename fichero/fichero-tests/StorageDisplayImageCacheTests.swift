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

    private func makeService() -> StorageServiceGenerated {
        StorageServiceGenerated(ficheroClient: FicheroClient(libraryPath: nil))
    }

    private func dummyImage() -> PlatformImage {
        #if os(macOS)
        return PlatformImage()
        #else
        return UIImage(systemName: "photo") ?? UIImage()
        #endif
    }

    @Test("display cache count never exceeds the limit")
    func displayCacheStaysBounded() {
        let service = makeService()
        let limit = StorageServiceGenerated.displayPlatformImageCacheLimit
        let img = dummyImage()
        for index in 0..<(limit + 10) {
            service.cacheDisplayPlatformImage(img, for: "doc-\(index)")
        }
        #expect(service.displayPlatformImageCacheCount == limit)
    }

    @Test("oldest display cache entries are evicted first; newest survive")
    func displayCacheEvictsOldestFirst() {
        let service = makeService()
        let limit = StorageServiceGenerated.displayPlatformImageCacheLimit
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
}
