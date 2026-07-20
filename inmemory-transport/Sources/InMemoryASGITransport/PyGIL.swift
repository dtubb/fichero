import Foundation
import PythonKit

/// A reference-type box around a `PythonObject` that keeps every Python refcount
/// operation on the GIL. `PythonObject` is a value type: copying it (assignment,
/// capture, returning it across a thread boundary) mutates CPython refcounts, and
/// doing that off the GIL is a data race that can corrupt the interpreter.
///
/// `PyRef` lets Swift pass a Python object between threads as an ordinary class
/// reference (ARC only — no Python touch). The wrapped object is only ever read
/// via `value` **while the caller holds the GIL**, and it is released on the GIL
/// in `deinit`, so no refcount ever changes without the GIL held.
///
/// Construct a `PyRef` only while holding the GIL (e.g. inside `PythonWorker.sync`
/// or a `PyGIL.ensure()` scope).
final class PyRef {
    private var object: PythonObject?

    /// Wrap `object`. MUST be called with the GIL held (this copies/retains it).
    init(_ object: PythonObject) { self.object = object }

    /// The wrapped object. Only touch the result while holding the GIL.
    var value: PythonObject { object! }

    deinit {
        // Releasing the last reference to the PythonObject decrements a CPython
        // refcount, which must happen on the GIL. Assigning nil performs that
        // release inside the ensured scope.
        let gil = PyGIL.ensure()
        object = nil
        PyGIL.release(gil)
    }
}

/// Direct bindings to CPython's GIL C-API, resolved from the already-loaded
/// libpython via `dlsym`. PythonKit does not manage the GIL for you, and a
/// dedicated worker thread that just sits in a Swift condition variable between
/// calls would otherwise **retain the GIL forever** — CPython only drops the GIL
/// at specific bytecode/​blocking points, and "parked in NSCondition.wait" is not
/// one of them. Any other thread that then needs the GIL (interpreter teardown,
/// leftover anyio/asyncio threadpool threads) deadlocks in `take_gil`.
///
/// So `PythonWorker` explicitly:
///  - releases the GIL once after interpreter init (`PyEval_SaveThread`), and
///  - re-acquires it only for the duration of each job (`PyGILState_Ensure` /
///    `PyGILState_Release`).
///
/// Between jobs the GIL is free, so finalization and background Python threads
/// can make progress.
enum PyGIL {
    private typealias EnsureFn = @convention(c) () -> Int32
    private typealias ReleaseFn = @convention(c) (Int32) -> Void
    private typealias SaveFn = @convention(c) () -> UnsafeMutableRawPointer?
    private typealias CheckFn = @convention(c) () -> Int32

    private static let handle = dlopen(nil, RTLD_LAZY)

    private static func sym<T>(_ name: String, as type: T.Type) -> T {
        guard let p = dlsym(handle, name) else {
            fatalError("InMemoryASGITransport: symbol \(name) not found in libpython")
        }
        return unsafeBitCast(p, to: T.self)
    }

    private static let ensureFn = sym("PyGILState_Ensure", as: EnsureFn.self)
    private static let releaseFn = sym("PyGILState_Release", as: ReleaseFn.self)
    private static let saveFn = sym("PyEval_SaveThread", as: SaveFn.self)
    private static let checkFn = sym("PyGILState_Check", as: CheckFn.self)

    /// Whether the current thread currently holds the GIL.
    static func held() -> Bool { checkFn() != 0 }

    /// Acquire the GIL for the current thread. Returns an opaque state token to
    /// pass to `release`. Reentrant-safe (refcounted per thread).
    static func ensure() -> Int32 { ensureFn() }

    /// Release the GIL previously acquired with `ensure`.
    static func release(_ state: Int32) { releaseFn(state) }

    /// Release the GIL held by the current thread after interpreter init, so it
    /// is available to every other thread. No-op if this thread does not hold the
    /// GIL (guards against `PyEval_SaveThread` aborting on a NULL thread state).
    static func releaseInitialGIL() {
        if held() { _ = saveFn() }
    }
}
