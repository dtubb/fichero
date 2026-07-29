import Foundation

/// Single Swift resolver for the shared, cross-layer fixture library.
///
/// The canonical specimen files live at the REPO root in `test-fixtures/files`
/// (shared with the engine's pytest suites, which resolve the same tree
/// through `fichero-server/tests/fixture_paths.py`). Resolution walks UP from
/// `#filePath`, so it is immune to this file — or callers — moving deeper in
/// the test tree, and works from any worktree checkout.
enum TestFixtures {
    /// `<repo>/test-fixtures/files`, or nil when no enclosing checkout is found.
    static var sampleFilesDirectory: URL? {
        var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        for _ in 0..<10 {
            let candidate = dir
                .appendingPathComponent("test-fixtures")
                .appendingPathComponent("files")
            if FileManager.default.fileExists(atPath: candidate.path) {
                return candidate
            }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    /// URL of one shared specimen. Throws (never returns a dangling URL) so a
    /// typo or unsynced checkout fails loudly at the call site.
    static func sampleFile(_ name: String) throws -> URL {
        guard let root = sampleFilesDirectory else {
            throw FixtureError.repoRootNotFound
        }
        let url = root.appendingPathComponent(name)
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw FixtureError.missing(name: name, at: url.path)
        }
        return url
    }

    enum FixtureError: Error, CustomStringConvertible {
        case repoRootNotFound
        case missing(name: String, at: String)

        var description: String {
            switch self {
            case .repoRootNotFound:
                return "TestFixtures: no test-fixtures/files directory above #filePath"
            case let .missing(name, path):
                return "TestFixtures: shared fixture \(name) missing at \(path)"
            }
        }
    }
}
