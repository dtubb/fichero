//
//  LibraryRowMetadataOptionsTests.swift
//  FicheroTests
//
//  Daniel, 2026-09-02, live on 2026.09.01.2:
//   · "List rows show a Completed status pill and a date — both OFF by
//      default, controlled from the Metadata menu, which must show
//      checkmarks reflecting the current show/hide state."
//   · "Add an option to show more lines of content per row (2 / 4 / 6)."
//

@testable import Fichero
import Foundation
import Testing

@Suite("Metadata options: what a list row shows")
struct LibraryRowMetadataOptionsTests {

    // MARK: - Status and Date are OFF by default

    @Test("the default row shows neither the status pill nor the date")
    func statusAndDateAreOffByDefault() {
        let defaults = LibraryRowAttribute.set(from: LibraryRowAttribute.defaultRaw)
        #expect(!defaults.contains(.status))
        #expect(!defaults.contains(.date))
        #expect(!defaults.contains(.type))
        // Entities stay ON, and the NAME is always on unless explicitly hidden.
        #expect(defaults.contains(.entities))
        #expect(defaults.contains(.name))
    }

    @Test("a stored value from before the ruling cannot survive it")
    func storageKeyIsVersioned() throws {
        // A default is only a default until something is stored. Daniel was
        // looking at an installed build whose stored CSV predated the ruling,
        // so the key is versioned — this pins that it moved, and that the view
        // reads the constant rather than a second literal that can drift.
        #expect(LibraryRowAttribute.storageKey == "library.rowAttributes.v2")
        let view = try AppSource.text("Views/Library/LibraryView.swift")
        #expect(view.contains("@AppStorage(LibraryRowAttribute.storageKey)"))
        #expect(!view.contains("@AppStorage(\"library.rowAttributes\")"),
                "the un-versioned key would keep serving the pre-ruling value")
    }

    @Test("the row renders status and date only when they are turned on")
    func rowGatesStatusAndDate() throws {
        let row = try AppSource.text("Views/Library/LibraryViewComponents.swift")
        #expect(row.contains("if visibleAttributes.contains(.date)"))
        #expect(row.contains("if visibleAttributes.contains(.status)"))
    }

    // MARK: - The menu shows state and toggles it

    @Test("every attribute is a Toggle, so the menu draws a real checkmark")
    func menuShowsCheckmarks() throws {
        let source = try AppSource.text("Views/Library/LibraryRowAttributes.swift")
        #expect(source.contains("Toggle(attribute.title, isOn: LibraryRowAttributes.binding("),
                Comment(rawValue: "a macOS menu renders a Toggle as a checkmark item "
                    + "and re-reads its binding each time it opens — the state display "
                    + "Daniel asked for"))
        #expect(!source.contains("Label(attribute.title, systemImage: \"checkmark\")"),
                "the tick belonged in the icon slot, which is not a checkmark affordance")
    }

    @Test("one binding behind both coats")
    func popoverAndMenuShareOneBinding() throws {
        let source = try AppSource.text("Views/Library/LibraryRowAttributes.swift")
        // The popover's own copy of the get/set is gone: two coats, one rule.
        #expect(source.contains("enum LibraryRowAttributes"))
        #expect(source.components(separatedBy: "LibraryRowAttribute.raw(from: set)").count - 1 == 1,
                Comment(rawValue: "the CSV round-trip must live in ONE place, or the "
                    + "popover and the menu can toggle differently"))
    }

    @Test("toggling round-trips through the CSV codec")
    func toggleRoundTrips() {
        var raw = LibraryRowAttribute.defaultRaw
        var set = LibraryRowAttribute.set(from: raw)

        set.insert(.status)
        raw = LibraryRowAttribute.raw(from: set)
        #expect(LibraryRowAttribute.set(from: raw).contains(.status))

        set.remove(.status)
        raw = LibraryRowAttribute.raw(from: set)
        #expect(!LibraryRowAttribute.set(from: raw).contains(.status))

        // Hiding the NAME survives the round trip too — it is stored as its
        // absence marker, which is the one asymmetric case in the codec.
        set.remove(.name)
        raw = LibraryRowAttribute.raw(from: set)
        #expect(!LibraryRowAttribute.set(from: raw).contains(.name))
    }

    // MARK: - More lines of content per row

    @Test("content lines offer 2 / 4 / 6 and default to 2")
    func contentLineChoices() {
        #expect(LibraryRowContentLines.allCases.map(\.rawValue) == [2, 4, 6])
        #expect(LibraryRowContentLines.defaultValue == .two)
        #expect(LibraryRowContentLines.two.title == "2 Lines")
    }

    @Test("an unknown stored value falls back instead of trapping")
    func contentLinesResolveUnknown() {
        #expect(LibraryRowContentLines.resolve(4) == .four)
        #expect(LibraryRowContentLines.resolve(0) == .two)
        #expect(LibraryRowContentLines.resolve(99) == .two)
        #expect(LibraryRowContentLines.resolve(-1) == .two)
    }

    @Test("the row reserves the chosen number of lines, still fixed-height")
    func rowReservesTheChosenLines() throws {
        let row = try AppSource.text("Views/Library/LibraryViewComponents.swift")
        #expect(row.contains(".lineLimit(contentLines, reservesSpace: true)"),
                Comment(rawValue: "reservesSpace is the #4191 density cap — a document "
                    + "whose transcript lands late must not re-pitch the list under a scroll"))
        #expect(!row.contains(".lineLimit(2, reservesSpace: true)"),
                "the hard-coded 2 is what the option replaces")
    }

    @Test("the line count is resolved once per pass and is part of row identity")
    func contentLinesRideTheRowChrome() throws {
        let list = try AppSource.text("Views/Library/ViewModes/List/LibraryView+ListView.swift")
        #expect(list.contains("let contentLines: Int"),
                "it is a row-WIDE setting, so it belongs in ListRowChrome with the others")
        #expect(list.components(separatedBy: "LibraryRowContentLines.resolve(").count - 1 == 1,
                "resolved once per render pass, never per row")

        let helpers = try AppSource.text("Views/Library/ViewModes/LibraryView+Helpers.swift")
        #expect(helpers.contains("var contentLines: Int = LibraryRowContentLines.defaultValue.rawValue"),
                Comment(rawValue: "without it in DocRowIdentity, .equatable() suppresses "
                    + "the redraw and changing the setting appears to do nothing"))
    }

    @Test("both coats of the control offer the content-lines choice")
    func bothCoatsOfferContentLines() throws {
        let source = try AppSource.text("Views/Library/LibraryRowAttributes.swift")
        // Popover (the bar) and Menu (the narrow-width overflow) — the metadata
        // control has vanished at narrow widths before (2026-08-29); a new
        // option must not reintroduce that gap.
        #expect(source.components(separatedBy: "ForEach(LibraryRowContentLines.allCases)").count - 1 == 2)

        let bar = try AppSource.text("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(bar.contains("contentLines: $rowContentLinesRaw"))
        let overflow = try AppSource.text("Views/Library/LibraryView+BottomActionBar.swift")
        #expect(overflow.contains("contentLines: $rowContentLinesRaw"))
    }
}
