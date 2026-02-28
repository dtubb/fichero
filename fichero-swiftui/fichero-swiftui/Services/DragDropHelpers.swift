import Foundation

/// Thread-safe array wrapper for concurrent operations
actor ThreadSafeArray<T> {
    private var array: [T] = []

    func append(_ element: T) {
        array.append(element)
    }

    func getAll() -> [T] {
        return array
    }

    var isEmpty: Bool {
        array.isEmpty
    }
}

/// Thread-safe value wrapper for concurrent operations
actor ThreadSafeValue<T> {
    private var value: T

    init(_ initialValue: T) {
        self.value = initialValue
    }

    func set(_ newValue: T) {
        self.value = newValue
    }

    func get() -> T {
        return value
    }
}

// MARK: - Atomic Counter for Thread Safety
final class AtomicInt: @unchecked Sendable {
    private var value: Int
    private let lock = NSLock()

    init(value: Int) {
        self.value = value
    }

    func incrementAndGet() -> Int {
        lock.lock()
        defer { lock.unlock() }
        value += 1
        return value
    }

    func get() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}
