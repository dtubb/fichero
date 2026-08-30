//
//  StorageThumbnailCacheTests.swift
//  FicheroTests
//
//  Bounded thumbnail-cache eviction (#719). The eager-prefetch path warms
//  StorageService.thumbnailCache for every image in a folder; this
//  verifies the cache stays bounded (FIFO, oldest-first) so a folder with
//  thousands of images can't grow it without limit.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import SwiftUI
import Testing

@MainActor
struct StorageThumbnailCacheTests {

    private func makeService() -> StorageService {
        StorageService(ficheroClient: FicheroClient(libraryPath: nil))
    }

    private let dummy = Image(systemName: "photo")

    @Test("cache count never exceeds the limit")
    func cacheStaysBounded() {
        let service = makeService()
        let limit = StorageService.thumbnailCacheLimit
        for index in 0..<(limit + 50) {
            service.cacheThumbnail(dummy, for: "doc-\(index)")
        }
        #expect(service.thumbnailCacheCount == limit)
    }

    @Test("oldest entries are evicted first; newest survive")
    func evictsOldestFirst() {
        let service = makeService()
        let limit = StorageService.thumbnailCacheLimit
        for index in 0..<(limit + 5) {
            service.cacheThumbnail(dummy, for: "doc-\(index)")
        }
        // doc-0...doc-4 were the first inserted → evicted.
        #expect(service.cachedThumbnail(for: "doc-0") == nil)
        #expect(service.cachedThumbnail(for: "doc-4") == nil)
        // doc-5 onward survive.
        #expect(service.cachedThumbnail(for: "doc-5") != nil)
        #expect(service.cachedThumbnail(for: "doc-\(limit + 4)") != nil)
    }

    @Test("re-caching an existing id does not grow order / double-evict")
    func reCachingSameIdIsStable() {
        let service = makeService()
        for _ in 0..<10 {
            service.cacheThumbnail(dummy, for: "stable")
        }
        #expect(service.thumbnailCacheCount == 1)
        #expect(service.cachedThumbnail(for: "stable") != nil)
    }

    @Test("invalidate removes the entry from cache and order")
    func invalidateClearsEntry() {
        let service = makeService()
        service.cacheThumbnail(dummy, for: "doc-a")
        service.cacheThumbnail(dummy, for: "doc-b")
        service.invalidateImageCache(for: "doc-a")
        #expect(service.cachedThumbnail(for: "doc-a") == nil)
        #expect(service.cachedThumbnail(for: "doc-b") != nil)
        #expect(service.thumbnailCacheCount == 1)
    }
}
