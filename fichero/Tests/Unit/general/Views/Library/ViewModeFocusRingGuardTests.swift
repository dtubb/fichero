import Foundation
import Testing

/// The stray focus ring (Daniel, 2026-09-05: "a blue focus ring draws around
/// the ENTIRE library pane" — screenshot-confirmed twice).
///
/// macOS 14+ makes a `.focusable()` ScrollView/List keyboard-focusable AND
/// paints a native ring around the whole container. Every library view mode
/// needs the focus (arrow-key navigation runs off `.onKeyPress`, which only
/// fires on a focused view) but none may draw the ring — panes draw no focus
/// ring of their own (ruling 2026-08-31). The pairing is `.focusable()` +
/// `.focusEffectDisabled()`, and DatasetCardsView shipped with the first and
/// not the second, so its cards grid rang the entire pane.
///
/// This is a source-scan guard over the whole view-mode tree, not the one file:
/// the bug is a class — any renderer that becomes focusable and forgets to
/// suppress its ring reintroduces it — so the guard sweeps every sibling.
struct ViewModeFocusRingGuardTests {
    /// Every `.swift` file under `Views/Library/ViewModes`.
    private func viewModeFiles() throws -> [URL] {
        let root = try AppSource.root().appendingPathComponent("Views/Library/ViewModes")
        guard let enumerator = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else { return [] }
        return enumerator.compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
    }

    @Test("every focusable library view-mode container disables its focus ring")
    func focusableContainersDisableTheRing() throws {
        let files = try viewModeFiles()
        // The sweep must have something to sweep — a moved tree would otherwise
        // pass vacuously (absence read as success).
        #expect(!files.isEmpty)

        var offenders: [String] = []
        for file in files {
            let code = AppSource.codeOnly(try String(contentsOf: file, encoding: .utf8))
            guard code.contains(".focusable(") else { continue }
            if !code.contains(".focusEffectDisabled(") {
                offenders.append(file.lastPathComponent)
            }
        }
        #expect(
            offenders.isEmpty,
            "These focusable view-mode containers draw a native focus ring — pair .focusable() with .focusEffectDisabled(): \(offenders.joined(separator: ", "))"
        )
    }

    /// The specific file the report was about, named so the regression is
    /// unmistakable if it ever comes back.
    @Test("DatasetCardsView pairs focusable with focusEffectDisabled")
    func datasetCardsSuppressesTheRing() throws {
        let source = try AppSource.code(
            "Views/Library/ViewModes/Dataset/Cards/DatasetCardsView.swift"
        )
        #expect(source.contains(".focusable()"))
        #expect(source.contains(".focusEffectDisabled()"))
    }
}
