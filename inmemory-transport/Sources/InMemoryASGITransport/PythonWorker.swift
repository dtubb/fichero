import Foundation
import PythonKit

/// The Python interpreter is single-threaded at heart: whichever OS thread first
/// touches CPython owns the Global Interpreter Lock (GIL), and PythonKit does not
/// acquire/release the GIL for you. Calling PythonKit from an arbitrary Swift
/// concurrency thread (where `await` may resume you anywhere) is therefore a
/// segfault waiting to happen.
///
/// `PythonWorker` pins ALL PythonKit interaction to one dedicated, long-lived
/// thread that owns the GIL. Work is submitted as closures via `sync(_:)` and
/// executed on that thread. This is the safe, boring way to drive PythonKit from
/// a multi-threaded Swift program.
///
/// Crucially, streaming still works: when the worker thread blocks inside a
/// Python `queue.Queue.get()` (see `AsgiBridge`), CPython releases the GIL for
/// the duration of the wait, so the *producer* Python thread (the one running the
/// ASGI app) is free to run and push the next chunk. The consumer (this worker)
/// wakes up as each chunk arrives — genuinely incremental, not buffered.
final class PythonWorker {
    static let shared = PythonWorker()

    private var thread: Thread!
    private let cond = NSCondition()
    private var queue: [() -> Void] = []
    private var ready = false

    /// The exec'd bridge module namespace (an object exposing `make_scope`,
    /// `make_driver`, `q_get`, `exec_module`). Only valid on the worker thread.
    ///
    /// Deliberately NOT initialised with a `Python.*` default: a stored-property
    /// default expression runs on whichever thread constructs `PythonWorker`
    /// (the caller of `.shared`), which would initialise CPython on the wrong
    /// thread and hand the GIL to it — then every worker-thread call segfaults.
    /// It is assigned exactly once, inside `setUpPython()` on the worker thread.
    private var _bridge: PythonObject?

    /// The bridge module. Only valid (and only touch it) on the worker thread.
    var bridge: PythonObject { _bridge! }

    private init() {
        thread = Thread { [weak self] in self?.runLoop() }
        thread.name = "InMemoryASGITransport.PythonWorker"
        thread.stackSize = 8 << 20
        thread.start()
        // Block until the interpreter + bridge are initialised.
        cond.lock()
        while !ready { cond.wait() }
        cond.unlock()
    }

    private func runLoop() {
        setUpPython()
        // Interpreter init left this thread holding the GIL. Drop it so the GIL
        // is free while we're idle; each job re-acquires it for its duration.
        PyGIL.releaseInitialGIL()

        cond.lock()
        ready = true
        cond.signal()
        cond.unlock()

        while true {
            cond.lock()
            while queue.isEmpty { cond.wait() }
            let job = queue.removeFirst()
            cond.unlock()

            // Hold the GIL only for the duration of the job. Blocking Python
            // calls inside the job (e.g. queue.Queue.get) release the GIL
            // internally, letting producer threads run.
            let gil = PyGIL.ensure()
            job()
            PyGIL.release(gil)
        }
    }

    /// Runs `body` on the worker thread and returns its result. Blocks the caller.
    func sync<T>(_ body: @escaping () -> T) -> T {
        if Thread.current === thread {
            // Re-entrant call from the worker thread itself: run inline.
            return body()
        }
        let box = ResultBox<T>()
        let done = NSCondition()
        var finished = false
        cond.lock()
        queue.append {
            let r = body()
            done.lock()
            box.value = r
            finished = true
            done.signal()
            done.unlock()
        }
        cond.signal()
        cond.unlock()

        done.lock()
        while !finished { done.wait() }
        let r = box.value!
        done.unlock()
        return r
    }

    // MARK: - Interpreter setup (runs once, on the worker thread)

    private func setUpPython() {
        let env = ProcessInfo.processInfo.environment

        // These must be set before PythonKit initialises CPython. We only touch
        // Python below, so setting them here (first Python access) is in time.
        let defaultLib =
            "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/Python"
        let defaultHome = "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12"
        if env["PYTHON_LIBRARY"] == nil {
            setenv("PYTHON_LIBRARY", defaultLib, 1)
        }
        if env["PYTHONHOME"] == nil, FileManager.default.fileExists(atPath: defaultHome) {
            setenv("PYTHONHOME", defaultHome, 1)
        }

        let sys = Python.import("sys")

        // Extra sys.path entries (dev venv site-packages + engine src) so the real
        // Fichero FastAPI app can be imported. Configurable via env for portability.
        let venvSite =
            env["FICHERO_VENV_SITE_PACKAGES"]
            ?? "/Users/danieltubb/code/fichero/.venv/lib/python3.12/site-packages"
        let engineSrc =
            env["FICHERO_ENGINE_SRC"] ?? "/Users/danieltubb/code/fichero/fichero-engine/src"
        for path in [venvSite, engineSrc] where FileManager.default.fileExists(atPath: path) {
            sys.path.insert(0, PythonObject(path))
        }

        // Exec the ASGI bridge into a fresh module namespace.
        let types = Python.import("types")
        let module = types.ModuleType("_inmemory_asgi_bridge")
        let builtins = Python.import("builtins")
        builtins.exec(PythonObject(AsgiBridge.source), module.__dict__)
        _bridge = module
    }

    private var exitGuardInstalled = false

    /// Some C-extension libraries an app imports (notably DuckDB) register a
    /// global object whose C++ destructor runs at process `exit()` via
    /// `__cxa_finalize` and calls `PyEval_SaveThread`, which aborts unless the
    /// GIL is held on the finalizing (main) thread. Because we deliberately leave
    /// the GIL free while idle, we re-acquire it for the current thread just
    /// before those destructors run.
    ///
    /// Destructors registered via `__cxa_atexit` run in **reverse registration
    /// order**, so this guard must be registered *after* the offending library
    /// has loaded — i.e. after the app import — for our handler to run before the
    /// library's destructor. Call this right after importing an app.
    func installExitGILGuard() {
        cond.lock()
        let already = exitGuardInstalled
        exitGuardInstalled = true
        cond.unlock()
        guard !already else { return }
        atexit {
            _ = PyGIL.ensure()  // acquire and intentionally never release
        }
    }
}

/// Tiny reference box so `sync` can ferry a value back across the thread boundary.
private final class ResultBox<T> {
    var value: T?
}
