import Foundation
import PythonKit

/// Helpers to obtain ASGI application objects on the `PythonWorker` thread.
///
/// All PythonKit access must happen on that one thread; these run there for you
/// and hand back the resulting `PythonObject`, which callers pass to
/// `InMemoryASGIClientTransport(app:)`.
public enum ASGIAppLoader {

    /// Exec a snippet of Python and return one of its module-level attributes
    /// (default `app`). Used to define synthetic ASGI apps in tests.
    public static func execApp(_ code: String, attribute: String = "app") -> PythonObject {
        PythonWorker.shared.sync {
            let module = PythonWorker.shared.bridge.exec_module(PythonObject(code))
            return module[dynamicMember: attribute]
        }
    }

    /// Import `attribute` from `module` (e.g. module: "fichero.api.main", attribute: "app").
    public static func importApp(module: String, attribute: String = "app") -> PythonObject {
        let app: PythonObject = PythonWorker.shared.sync {
            let mod = Python.import(module)
            return mod[dynamicMember: attribute]
        }
        // Register the exit-time GIL guard now, after the module (and any C
        // extensions such as DuckDB) have loaded, so our atexit handler runs
        // before their static destructors. See PythonWorker.installExitGILGuard.
        PythonWorker.shared.installExitGILGuard()
        return app
    }
}
