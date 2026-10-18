import XCTest

/// spec: modes-to-panes §`m2p.ios.no-tvos-branches` (iOS I1). tvOS is not a target; a branch on it
/// is dead code that hides what the iOS build really compiles.
final class NoTvOSBranchesTests: XCTestCase {

    func testNoSourceBranchesOnTvOS() throws {
        let root = try AppSource.root()
        var offenders: [String] = []
        for dir in ["Views", "Services"] {
            guard let walker = FileManager.default.enumerator(at: root.appendingPathComponent(dir), includingPropertiesForKeys: nil)
            else { continue }
            for case let url as URL in walker where url.pathExtension == "swift" {
                let lines = try String(contentsOf: url, encoding: .utf8).components(separatedBy: "\n")
                if lines.contains(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("#") && $0.contains("os(tvOS)") }) {
                    offenders.append(url.lastPathComponent)
                }
            }
        }
        XCTAssertEqual(offenders, [], "tvOS is not a target; remove its #if branches (iOS I1).")
    }
}
