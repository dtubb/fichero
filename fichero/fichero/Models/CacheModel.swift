import Observation
import SwiftUI

/// Simple cache model for storing computed data
/// Note: SwiftUI automatically caches Images, so icon caching is unnecessary
@MainActor
@Observable
class CacheModel {

    // MARK: - Data Cache

    /// Simple in-memory cache for computed data (not UI elements)
    /// Uses NSCache for automatic memory management under pressure
    private let dataCache = NSCache<NSString, AnyObject>()

    /// Maximum number of items to cache (prevents unbounded growth)
    private let maxCacheSize = 500

    init() {
        dataCache.countLimit = maxCacheSize
    }

    /// Cache a value with type safety
    /// - Parameters:
    ///   - value: Value to cache (must be a class type or wrapped)
    ///   - key: Cache key (validated for reasonable length)
    func cache<T: AnyObject>(_ value: T, forKey key: String) {
        // Validate key length to prevent memory issues
        guard key.count <= 256 else {
            return
        }
        dataCache.setObject(value, forKey: key as NSString)
    }

    /// Cache a struct value by wrapping it
    func cacheValue<T>(_ value: T, forKey key: String) {
        guard key.count <= 256 else {
            return
        }
        let wrapper = CacheWrapper(value: value)
        dataCache.setObject(wrapper, forKey: key as NSString)
    }

    /// Get cached class value
    func getCached<T: AnyObject>(forKey key: String) -> T? {
        return dataCache.object(forKey: key as NSString) as? T
    }

    /// Get cached struct value
    func getCachedValue<T>(forKey key: String) -> T? {
        guard let wrapper = dataCache.object(forKey: key as NSString) as? CacheWrapper<T> else {
            return nil
        }
        return wrapper.value
    }

    /// Remove cached value
    func removeCached(forKey key: String) {
        dataCache.removeObject(forKey: key as NSString)
    }

    /// Clear all cached data
    func clearCache() {
        dataCache.removeAllObjects()
    }

    // MARK: - Memory Management

    /// Clear cache when memory pressure occurs
    /// NSCache handles this automatically, but this allows manual clearing
    func handleMemoryWarning() {
        clearCache()
    }
}

/// Type-safe wrapper for caching non-class types
private final class CacheWrapper<T>: NSObject {
    let value: T

    init(value: T) {
        self.value = value
        super.init()
    }
}
