//
//  RequiresEngine.swift
//  FicheroUITests
//
//  #4238: a UI test whose precondition is missing does not fail — it POLLS.
//
//  `ColdLaunchReachesLibraryUITests` waits up to 120s for
//  `library.content.ready`, checking four times a second. Every check runs
//  `app.descendants(matching: .any)` and XCUITest then does "Capturing element
//  debug description" — serialising the ENTIRE element hierarchy to text. With
//  no embedded engine the library never becomes ready, so the loop runs to its
//  full deadline. Observed: the test host reached 56 GB and the machine became
//  unusable, twice.
//
//  The suite is RIGHT to require an embedded engine — that is the shipping
//  configuration, and testing it is the whole point (#4226). It is wrong about
//  what to do when the build cannot supply one. This check answers that
//  question in milliseconds, by looking at the product that was actually built,
//  and FAILS rather than skipping: a skipped launch test means the launch path
//  has no coverage, which is how sharing shipped broken in every release.
//

import XCTest

enum RequiresEngine {

    /// Fail immediately unless the built app really contains an embedded engine.
    ///
    /// Deliberately NOT a skip. A skip would make Debug runs green while the
    /// shipping launch path went untested — the exact failure this suite exists
    /// to catch. A fast, explicit failure says "you are running this in a scheme
    /// that cannot test it" in under a second, instead of after 120s and 56 GB.
    ///
    /// Note `start_backend.sh` does not satisfy this: that is an EXTERNAL HTTPS
    /// engine, and `--uitesting-embedded` has already told the app to use the
    /// bundled one. The message says so, because that is the first thing anyone
    /// tries.
    static func requireEmbeddedEngine(
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        guard let app = builtAppURL() else {
            XCTFail(
                "Could not locate the built Fichero.app next to the UI-test "
                + "bundle, so the embedded engine could not be verified (#4238).",
                file: file, line: line
            )
            throw PreconditionFailure.appNotFound
        }

        // Both embed locations: Resources for Developer-ID/DMG builds,
        // Helpers for the sandboxed Mac App Store build (TN2206).
        //
        // Check for the EXECUTABLE, not the bundle. The observed failure was a
        // hollow bundle: `Fichero Engine.app` present (1.3 GB of Resources) but
        // `Contents/MacOS/` empty, so an existence check on the .app passes
        // while exec fails — exactly the vacuous guard this file warns against.
        let candidates = [
            app.appendingPathComponent("Contents/Resources/Fichero Engine.app"),
            app.appendingPathComponent("Contents/Helpers/Fichero Engine.app"),
        ]
        guard candidates.contains(where: hasExecutable(bundle:)) else {
            XCTFail(
                """
                No runnable embedded engine in \(app.lastPathComponent), so \
                --uitesting-embedded can never reach library.content.ready. \
                (A bundle may exist but be HOLLOW — Contents/MacOS empty — \
                after an interrupted `briefcase build macOS`; rebuild it.)

                This scheme does not bundle an engine. Run this suite from an \
                embedded scheme (Dev Embedded / Beta Embedded).

                Starting fichero-server/scripts/start_backend.sh does NOT help: \
                that is an external HTTPS engine, and the launch argument \
                selects the embedded one.

                Failing now rather than polling — this suite snapshots the whole \
                accessibility tree ~4x/sec for 120s, which reached 56 GB (#4238).
                """,
                file: file, line: line
            )
            throw PreconditionFailure.engineNotEmbedded
        }
    }

    enum PreconditionFailure: Error {
        case appNotFound
        case engineNotEmbedded
    }

    /// True only when the engine bundle contains at least one executable in
    /// `Contents/MacOS` — the thing `Process.run` actually needs.
    private static func hasExecutable(bundle: URL) -> Bool {
        let macOS = bundle.appendingPathComponent("Contents/MacOS")
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: macOS.path) else {
            return false
        }
        return entries.contains { entry in
            let path = macOS.appendingPathComponent(entry).path
            // isExecutableFile is access(X_OK), which is TRUE for directories
            // (mode 755) — a folder in MacOS/ must not satisfy the guard.
            var isDirectory: ObjCBool = false
            return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
                && !isDirectory.boolValue
                && FileManager.default.isExecutableFile(atPath: path)
        }
    }

    /// The UI-test bundle sits inside the runner app, which lives beside the
    /// app under test in the same Products directory.
    private static func builtAppURL() -> URL? {
        var dir = Bundle(for: Probe.self).bundleURL
        // …/Products/<Config>/FicheroUITests-Runner.app/PlugIns/FicheroUITests.xctest
        for _ in 0..<5 {
            dir = dir.deletingLastPathComponent()
            let candidate = dir.appendingPathComponent("Fichero.app")
            if FileManager.default.fileExists(atPath: candidate.path) { return candidate }
        }
        return nil
    }

    /// Anchor class so `Bundle(for:)` resolves to the UI-test bundle.
    private final class Probe {}
}
