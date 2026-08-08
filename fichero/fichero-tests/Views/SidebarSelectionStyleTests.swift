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
/// `@MainActor` is LOAD-BEARING, for the reason recorded on
/// `LibraryView.isAwaitingFirstLoad`: `LibrarySelectionStyle.fill` reads
/// `NSColor.unemphasizedSelectedContentBackgroundColor`, and the Swift Testing
/// suite runs on a cooperative thread. Touching AppKit colour from off-main has
/// SIGTRAPped this test process before, nondeterministically and misattributed
/// to whichever test happened to be running (#4201).
@MainActor
struct SidebarSelectionStyleTests {

    // MARK: - Finder's selection grammar (Daniel, 2026-08-08)

    /// Supersedes #4371's "selection changes nothing": like Finder's sidebar
    /// and Mail's mailbox list, the grey fill carries the ROW and the NAME
    /// takes the system accent when selected. Weight never changes — the
    /// accent is the signal, and white-on-accent stays reserved for the
    /// DROP target.
    @Test("a selected label takes the accent colour, an unselected one stays primary")
    func selectionTintsTheLabelAccent() {
        #expect(LibrarySelectionStyle.sidebarLabel(isSelected: true).color == .accentColor)
        #expect(LibrarySelectionStyle.sidebarLabel(isSelected: false).color == .primary)
    }

    @Test("the label is never white — the inversion belongs to the drop target only")
    func labelIsNeverWhite() {
        for isSelected in [true, false] {
            let style = LibrarySelectionStyle.sidebarLabel(isSelected: isSelected)
            #expect(style.color != .white, "isSelected: \(isSelected)")
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

    private static func sidebarRoot() throws -> URL {
        try AppSource.root().appendingPathComponent("Views/Sidebar")
    }

    private static func sidebarSwiftFiles() throws -> [URL] {
        guard let enumerator = FileManager.default.enumerator(
            at: try sidebarRoot(),
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
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The row must state its label treatment rather than inherit the native
    /// inversion, and it must read it from the shared vocabulary.
    @Test("the sidebar row applies the shared label style explicitly")
    func sidebarRowAppliesTheSharedStyle() throws {
        let source = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift")
        #expect(source.contains("LibrarySelectionStyle.sidebarLabel(isSelected:"))
        // The one content-colour rule (rowContentColor, Daniel's preview
        // review 2026-08-08): white ONLY while a drop targets the row (the
        // one solid-accent platter left), otherwise the shared style's
        // colour. No prominence switch — the selected platter is the grey
        // fill sidebarDropHighlight paints itself, never the native
        // emphasized accent, so the content never needs to invert.
        #expect(source.contains(".foregroundStyle(rowContentColor)"))
        #expect(!source.contains("backgroundProminence"))
        #expect(source.contains(".fontWeight(rowLabelStyle.weight)"))
    }

    /// The system's own selection fill is tinted to the shared colour, so the
    /// native treatment and the app's vocabulary agree instead of fighting.
    @Test("the sidebar list keeps the NATIVE source-list selection — no tint")
    func sidebarListKeepsNativeSelection() throws {
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        // #4563 (2026-08-08): the #4371 tint did not hold for the FOCUSED
        // selection on the current SDK — the platter rendered saturated
        // accent ("bright green background"). The native .sidebar selection
        // is Finder's grey material in both focus states; no tint may wrap
        // it again without a new decision from Daniel.
        #expect(!source.contains(".tint(LibrarySelectionStyle.fill)"))
        // Still a native sidebar List — the fix is removing the override,
        // not a rewrite.
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
