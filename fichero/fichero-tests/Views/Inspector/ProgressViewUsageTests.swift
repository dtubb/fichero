import XCTest

/// #4447: this used to check three NAMED files for a banned pattern
/// (`ProgressView().scaleEffect(0.6).frame(`) — a fourth file reintroducing
/// it would have sailed through untested, which is the exact "new file
/// breaks the invariant and nothing notices" shape the issue is about. The
/// invariant is about the app ("indeterminate progress views don't use fixed
/// frames"), not about three specific files, so it now scans the whole
/// `Views/` directory.
final class ProgressViewUsageTests: XCTestCase {
    func testNoIndeterminateProgressViewUsesAFixedFrame() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views")

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" } ?? []
        XCTAssertFalse(files.isEmpty, "the sweep must actually read files")

        var offenders: [String] = []
        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            if source.contains("ProgressView().scaleEffect(0.6).frame(") {
                offenders.append(file.lastPathComponent)
            }
        }
        XCTAssertTrue(offenders.isEmpty, "fixed-frame indeterminate ProgressView in: \(offenders.joined(separator: ", "))")
    }

    /// The three sites the old file-named version knew about, still asserted
    /// positively — locks that the sanctioned `.controlSize(.mini)` shape
    /// (not just the absence of the banned one) is actually present where it
    /// was reported.
    func testKnownIndeterminateProgressSitesUseControlSizeMini() throws {
        for relativePath in [
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Prototype.swift",
            "Views/Components/NodeClassPicker.swift",
            "Views/Workflow/Nodes/NodeConfigs/ExtractEntitiesNodeConfig.swift"
        ] {
            let source = try Self.appSource(relativePath)
            XCTAssertTrue(
                source.contains("ProgressView().controlSize(.mini)"),
                "\(relativePath) no longer uses the sanctioned indeterminate style"
            )
        }
    }

    /// #4447: a named-file guard whose path doesn't exist must fail loudly
    /// as "this guard is now vacuous", not with a raw NSCocoaErrorDomain
    /// error that reads like a harness problem.
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        guard FileManager.default.fileExists(atPath: url.path) else {
            XCTFail("appSource: no file at \(relativePath) — this guard is now vacuous, not passing")
            throw CocoaError(.fileReadNoSuchFile)
        }
        return try String(contentsOf: url, encoding: .utf8)
    }
}
