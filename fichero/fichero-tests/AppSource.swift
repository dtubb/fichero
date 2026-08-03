import Foundation

/// The app's source tree, resolved once, with a floor (#4493).
///
/// ## The bug this replaces
///
/// 99 test files resolve the app source themselves, in **10 different depth
/// shapes**, by counting `deletingLastPathComponent()` calls from `#filePath`
/// and appending a hand-written suffix. Two of those counts are wrong today:
///
/// - `WorkflowStreamEndReconciliationTests` deletes three then appends
///   `"../fichero"`, landing on `<repo>/fichero` — one level SHORT;
/// - `ClaimStoreRoutingTests` deletes three then appends `"fichero/fichero"`,
///   landing on `<repo>/fichero/fichero/fichero` — one level DEEP.
///
/// Same copied idiom, wrong in opposite directions, in files written by
/// different people on different days. That is what makes it a class rather
/// than two typos.
///
/// ## Why this one cannot be wrong the same way
///
/// **It does not count anything.** It walks UP from `#filePath` until it finds
/// a directory containing the landmark, so the answer does not depend on how
/// deep the calling test happens to sit. Move a test file into a new
/// subdirectory and it keeps working — which is precisely the edit that breaks
/// a hardcoded depth, and precisely the edit nobody remembers to check.
///
/// ## The floor
///
/// If the walk finds nothing, this throws with the path it started from and
/// the landmark it wanted — it does not return a plausible-looking URL that
/// then fails later as a file-not-found inside an unrelated assertion.
///
/// That is the #4487 rule in the test suite: a helper that reads source and
/// cannot find it is BLIND, and blind must be legible. The copies fail as a
/// thrown `NSCocoaErrorDomain` read error naming a path nobody recognises,
/// three tests at a time, with no statement of what was being looked for.
enum AppSource {

    /// A path that exists in the app target and nowhere else, used to
    /// recognise the root. Deliberately a directory that has been stable for
    /// the life of the project rather than a single file, which a rename would
    /// silently invalidate.
    static let landmark = "Models"

    /// Thrown instead of returning a wrong-but-plausible root.
    struct NotFound: Error, CustomStringConvertible {
        let startedFrom: String
        let landmark: String

        var description: String {
            """
            AppSource: BLIND — could not locate the app source root.
              walked up from: \(startedFrom)
              looking for a directory containing: fichero/\(landmark)
            The test tree moved relative to the app target. This is not a \
            missing file — it is a missing ROOT, and every source-reading \
            assertion below it would otherwise fail as an unrelated read error.
            """
        }
    }

    /// The `fichero/fichero` directory, found by walking up rather than by
    /// counting path components.
    /// `String`, not `StaticString`. `#filePath` satisfies both, but only
    /// `String` also accepts a synthesised path — and the test that proves
    /// depth-independence has to synthesise one, because there is no real file
    /// at every nesting level to call from.
    ///
    /// A `StaticString` parameter would make the walk untestable at the exact
    /// property it exists to guarantee.
    static func root(from filePath: String = #filePath) throws -> URL {
        let start = URL(fileURLWithPath: filePath)
        var directory = start.deletingLastPathComponent()

        while directory.path != "/" {
            let candidate = directory.appendingPathComponent("fichero")
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(
                atPath: candidate.appendingPathComponent(landmark).path,
                isDirectory: &isDirectory
            ), isDirectory.boolValue {
                return candidate
            }
            directory = directory.deletingLastPathComponent()
        }

        throw NotFound(startedFrom: start.path, landmark: landmark)
    }

    /// The text of an app source file, relative to the app target root.
    ///
    /// Failures are separated on purpose: a missing ROOT is `NotFound` above,
    /// a missing FILE is the underlying read error. Conflating them is how the
    /// copies made a moved tree look like a deleted file.
    static func text(
        _ relativePath: String,
        from filePath: String = #filePath
    ) throws -> String {
        let url = try root(from: filePath).appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
