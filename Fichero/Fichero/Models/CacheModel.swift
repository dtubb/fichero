import SwiftUI

/// Simple cache model for storing computed data
/// Note: SwiftUI automatically caches Images, so icon caching is unnecessary
@MainActor
class CacheModel: ObservableObject {

    // MARK: - Data Cache

    /// Simple in-memory cache for computed data (not UI elements)
    private var dataCache: [String: Any] = [:]

    /// Cache a value
    func cache<T>(_ value: T, forKey key: String) {
        dataCache[key] = value
    }

    /// Get cached value
    func getCached<T>(forKey key: String) -> T? {
        return dataCache[key] as? T
    }

    /// Remove cached value
    func removeCached(forKey key: String) {
        dataCache.removeValue(forKey: key)
    }

    /// Clear all cached data
    func clearCache() {
        dataCache.removeAll()
    }

    // MARK: - Memory Management

    /// Clear cache when memory pressure occurs
    /// In SwiftUI apps, the system handles most memory management automatically
    func handleMemoryWarning() {
        clearCache()
    }
}
