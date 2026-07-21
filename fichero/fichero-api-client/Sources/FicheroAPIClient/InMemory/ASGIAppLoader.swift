#if os(macOS)
import Foundation
import PythonKit

/// An opaque, GIL-safe handle to a Python ASGI application object.
///
/// Callers hold this as a plain class reference (ARC only) and never touch the
/// underlying `PythonObject` directly — the transport dereferences it on the
/// worker thread while holding the GIL. This keeps Python refcounting off any
/// thread that doesn't own the GIL (WARN-2).
public final class ASGIApp {
    let ref: PyRef
    init(ref: PyRef) { self.ref = ref }
}

/// Helpers to obtain ASGI application handles on the `PythonWorker` thread.
///
/// All PythonKit access happens on that one thread; these run there and hand back
/// an `ASGIApp` handle to pass to `InMemoryASGIClientTransport(app:)`.
public enum ASGIAppLoader {

    /// Exec a snippet of Python and return one of its module-level attributes
    /// (default `app`). Used to define synthetic ASGI apps in tests.
    public static func execApp(_ code: String, attribute: String = "app") -> ASGIApp {
        PythonWorker.shared.sync {
            let module = PythonWorker.shared.bridge.exec_module(PythonObject(code))
            return ASGIApp(ref: PyRef(module[dynamicMember: attribute]))
        }
    }

    /// Import `attribute` from `module` (e.g. module: "fichero.api.main", attribute: "app").
    public static func importApp(module: String, attribute: String = "app") -> ASGIApp {
        let handle: ASGIApp = PythonWorker.shared.sync {
            let mod = Python.import(module)
            return ASGIApp(ref: PyRef(mod[dynamicMember: attribute]))
        }
        // Register the exit-time GIL guard now, after the module (and any C
        // extensions such as DuckDB) have loaded, so our atexit handler runs
        // before their static destructors. See PythonWorker.installExitGILGuard.
        PythonWorker.shared.installExitGILGuard()
        return handle
    }
}
#endif
