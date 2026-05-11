@testable import Fichero
import XCTest

/// Tests for the in-memory cache model used across the app for memoising
/// computed values. NSCache-backed, type-safe class + struct wrappers.
@MainActor
final class CacheModelTests: XCTestCase {

    // MARK: - Class object caching

    func testCacheAndRetrieveClassValue() {
        let cache = CacheModel()
        let value = NSString(string: "hello")
        cache.cache(value, forKey: "k1")
        let retrieved: NSString? = cache.getCached(forKey: "k1")
        XCTAssertEqual(retrieved, "hello")
    }

    func testGetCachedClassValueMissReturnsNil() {
        let cache = CacheModel()
        let retrieved: NSString? = cache.getCached(forKey: "nope")
        XCTAssertNil(retrieved)
    }

    // MARK: - Struct value caching (wrapper path)

    func testCacheAndRetrieveStructValue() {
        let cache = CacheModel()
        struct Sample: Equatable { let id: Int; let name: String }
        let value = Sample(id: 42, name: "Asprilla")
        cache.cacheValue(value, forKey: "person")
        let retrieved: Sample? = cache.getCachedValue(forKey: "person")
        XCTAssertEqual(retrieved, value)
    }

    func testGetCachedStructValueMissReturnsNil() {
        let cache = CacheModel()
        struct Sample { let x: Int }
        let retrieved: Sample? = cache.getCachedValue(forKey: "nope")
        XCTAssertNil(retrieved)
    }

    // MARK: - Type safety

    func testWrongTypeRetrievalReturnsNil() {
        let cache = CacheModel()
        let value = NSString(string: "hello")
        cache.cache(value, forKey: "k1")
        // Asking for the wrong type → nil, not a crash.
        let wrong: NSNumber? = cache.getCached(forKey: "k1")
        XCTAssertNil(wrong)
    }

    // MARK: - Key length validation

    func testOversizedKeyRejectedSilently() {
        let cache = CacheModel()
        let oversized = String(repeating: "k", count: 257)
        cache.cache(NSString(string: "x"), forKey: oversized)
        // Nothing crashes; nothing is retrievable.
        let retrieved: NSString? = cache.getCached(forKey: oversized)
        XCTAssertNil(retrieved)
    }

    func testOversizedKeyForStructValueRejectedSilently() {
        let cache = CacheModel()
        let oversized = String(repeating: "k", count: 257)
        cache.cacheValue(42, forKey: oversized)
        let retrieved: Int? = cache.getCachedValue(forKey: oversized)
        XCTAssertNil(retrieved)
    }
}
