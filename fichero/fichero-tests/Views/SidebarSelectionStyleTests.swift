@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// #4371: sidebar selection must read like Finder and Mail — a subtle row
/// fill, the label in its standard colour and weight, and the icon keeping its
/// own semantic colour.
///
/// The premise that made this bug invisible for a while is recorded in
/// `LibrarySelectionStyle`'s doc comment: the #4191 work assumed the native
/// `.listStyle(.sidebar)` List "already renders this treatment". It does not.
/// The native emphasized source-list selection paints a saturated accent bar
/// and forces the label white and bold. The sidebar was already 100% native —
/// there is no hand-rolled fill anywhere under `Views/Sidebar` — so "prefer
/// native" was satisfied and the appearance was still wrong.
struct SidebarSelectionStyleTests {

    // MARK: - Selection does not touch the label

    /// Daniel's two named defects, as one equality: selecting a row must
    /// change NOTHING about its label. If a future change makes selection
    /// bold or re-colour the text, this is the assertion that fails.
    @Test("selection changes nothing about the label")
    func selectionDoesNotChangeTheLabel() {
        #expect(
            LibrarySelectionStyle.sidebarLabel(isSelected: true)
                == LibrarySelectionStyle.sidebarLabel(isSelected: false)
        )
    }

    @Test("the label keeps the standard text colour, never white or accent")
    func labelKeepsStandardColour() {
        for isSelected in [true, false] {
            let style = LibrarySelectionStyle.sidebarLabel(isSelected: isSelected)
            #expect(style.color == .primary, "isSelected: \(isSelected)")
            #expect(style.color != .white)
            #expect(style.color != .accentColor)
        }
    }

    @Test("the label keeps regular weight, never bolded by selection")
    func labelKeepsRegularWeight() {
        for isSelected in [true, false] {
            let style = LibrarySelectionStyle.sidebarLabel(isSelected: isSelected)
            #expect(style.weight == .regular, "isSelected: \(isSelected)")
            #expect(style.weight != .bold)
            #expect(style.weight != .semibold)
        }
    }

    // MARK: - One selection vocabulary

    /// The sidebar must not become a third selection language. Its fill is the
    /// same token the library list, icon tiles and table rows already use.
    @Test("the sidebar fill is the shared system unemphasized colour")
    func sidebarFillIsTheSharedToken() {
        #if os(macOS)
        #expect(LibrarySelectionStyle.fill == Color(nsColor: .unemphasizedSelectedContentBackgroundColor))
        #endif
        // Not a hand-picked accent or opacity — the system colour tracks
        // light/dark, increased contrast and the user's accent for free.
        #expect(LibrarySelectionStyle.fill != .accentColor)
        #expect(LibrarySelectionStyle.fill != Color.accentColor.opacity(0.12))
    }

    /// The library's own focus-dependent label tint is untouched by this
    /// change — the sidebar rule is additional vocabulary, not a redefinition
    /// of the existing one (#4191 stays intact).
    @Test("the library's focus-dependent label tint is unchanged")
    func libraryLabelTintIsUnchanged() {
        #expect(LibrarySelectionStyle.labelTint(focused: true) == .accentColor)
        #expect(LibrarySelectionStyle.labelTint(focused: false) == .secondary)
    }

    // MARK: - Structural: no second selection language in the sidebar

    private static var sidebarRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar")
    }

    private static func sidebarSwiftFiles() throws -> [URL] {
        guard let enumerator = FileManager.default.enumerator(
            at: sidebarRoot,
            includingPropertiesForKeys: nil
        ) else { return [] }
        var files: [URL] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            files.append(url)
        }
        return files
    }

    /// The sidebar tree must not grow its own selection fill. `Modes/` is
    /// excluded on purpose: the mode BAR is a segmented control, not a list of
    /// items, and its accent treatment is a different thing entirely.
    @Test("no sidebar item row paints its own selection fill")
    func noSidebarRowPaintsItsOwnSelectionFill() throws {
        let files = try Self.sidebarSwiftFiles()
        #expect(!files.isEmpty, "Could not enumerate the sidebar sources")

        var offenders: [String] = []
        for url in files where !url.path.contains("/Sidebar/Modes/") {
            let source = try String(contentsOf: url, encoding: .utf8)
            let name = url.lastPathComponent
            // A selection-driven accent fill or a forced white label is the
            // #4360 class of bug: painting over the system's own treatment.
            if source.contains("isSelected ? Color.accentColor") {
                offenders.append("\(name): accent selection fill")
            }
            if source.contains("isSelected ? .white") || source.contains("isSelected ? Color.white") {
                offenders.append("\(name): forced white label")
            }
            if source.contains("isSelected ? .bold") || source.contains("isSelected ? Font.Weight.bold") {
                offenders.append("\(name): bolded on selection")
            }
        }
        #expect(offenders.isEmpty, "\(offenders)")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The row must state its label treatment rather than inherit the native
    /// inversion, and it must read it from the shared vocabulary.
    @Test("the sidebar row applies the shared label style explicitly")
    func sidebarRowAppliesTheSharedStyle() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        #expect(source.contains("LibrarySelectionStyle.sidebarLabel(isSelected:"))
        #expect(source.contains(".foregroundStyle(rowLabelStyle.color)"))
        #expect(source.contains(".fontWeight(rowLabelStyle.weight)"))
    }

    /// The system's own selection fill is tinted to the shared colour, so the
    /// native treatment and the app's vocabulary agree instead of fighting.
    @Test("the sidebar list tints the native selection to the shared fill")
    func sidebarListTintsTheNativeSelection() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        #expect(source.contains(".tint(LibrarySelectionStyle.fill)"))
        // Still a native sidebar List — the fix is the colour, not a rewrite.
        #expect(source.contains(".listStyle(.sidebar)"))
        #expect(source.contains("List(selection: sidebarSelectionBinding)"))
    }

    /// The stale premise is corrected where it lived, so the next reader does
    /// not re-derive it.
    @Test("the shared style no longer claims the native sidebar already matches")
    func staleNativePremiseIsCorrected() throws {
        let source = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        #expect(!source.contains("which already\n/// renders this treatment"))
        #expect(source.contains("#4371"))
    }
}
