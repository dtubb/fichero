import XCTest

/// spec: xcode-build-configs §`build.ios-target-compiles-without-macos-only-types` (#5322).
/// `Process` exists only on macOS, so the engine process handle in `EmbeddedBackendService` must
/// sit behind `#if os(macOS)`; a bare use stops the iOS target compiling. A source scan, because
/// the Mac build cannot see the iOS-only failure.
final class IOSTargetMacOnlyTypesGuardrailTests: XCTestCase {

    func testBackendProcessIsGuardedForMacOSOnly() throws {
        let root = try AppSource.root()
        for file in ["EmbeddedBackendService.swift", "EmbeddedBackendService+Lifecycle.swift"] {
            let lines = try String(
                contentsOf: root.appendingPathComponent("Services/\(file)"), encoding: .utf8
            ).components(separatedBy: "\n")
            for (index, line) in lines.enumerated() where line.contains("backendProcess") {
                let previous = lines[..<index].last { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
                XCTAssertEqual(
                    previous?.trimmingCharacters(in: .whitespaces), "#if os(macOS)",
                    "\(file):\(index + 1) uses backendProcess (a macOS-only Process) outside #if os(macOS) (#5322)")
            }
        }
    }
}
