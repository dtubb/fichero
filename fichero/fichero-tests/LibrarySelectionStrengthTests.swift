import XCTest

/// Guardrail for the Mail-style selection treatment (#4191, superseding the
/// #3875 solid-accent fill). Daniel: selected row = SUBTLE GREY rounded-rect
/// fill with the label/icon tinted accent when the pane is focused — never a
/// solid accent fill, never white-on-accent text. The focused/unfocused
/// split survives (HIG: only key-window controls carry color), expressed in
/// the LABEL tint instead of the fill. These source-reading assertions lock
/// that in so a future edit can't quietly reintroduce either old idiom.
final class LibrarySelectionStrengthTests: XCTestCase {
    func testSelectionFillIsTheSharedGreyInBothFocusStates() throws {
        let components = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        // ONE shared token: AppKit's unemphasized selection color, so
        // light/dark and increased-contrast track the system.
        XCTAssertTrue(
            components.contains("enum LibrarySelectionStyle"),
            "The shared Mail-style selection tokens must exist (#4191)."
        )
        XCTAssertTrue(
            components.contains("unemphasizedSelectedContentBackgroundColor"),
            "The selection fill must be the system's unemphasized (grey) selection color (#4191)."
        )

        let helpers = try Self.appSource("Views/Library/ViewModes/LibraryView+Helpers.swift")
        XCTAssertTrue(
            helpers.contains("LibrarySelectionStyle.fill"),
            "List rows must draw the shared grey fill (#4191)."
        )
        XCTAssertTrue(
            helpers.contains("RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)"),
            "The list-row fill must be a rounded rect like Mail's, not an edge-to-edge wash (#4191)."
        )

        // The old #3875 solid-accent focused fill must be gone everywhere.
        let displayHelpers = try Self.appSource("Views/Library/ViewModes/LibraryView+DisplayHelpers.swift")
        XCTAssertFalse(
            displayHelpers.contains("Color.accentColor.opacity(0.85)"),
            "The #3875 solid-accent focused fill must not come back (#4191)."
        )
    }

    func testFocusSplitLivesInTheLabelTint() throws {
        // Focused pane → accent label; unfocused pane → secondary label.
        let displayHelpers = try Self.appSource("Views/Library/ViewModes/LibraryView+DisplayHelpers.swift")
        XCTAssertTrue(
            displayHelpers.contains("isPaneFocused ? .accentColor : .secondary"),
            "selectionTint must keep the focused/unfocused split in the label (#4191, HIG)."
        )
        let components = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        XCTAssertTrue(
            components.contains("LibrarySelectionStyle.labelTint(focused: isPaneFocused)"),
            "The list-row title must take the accent tint from the shared style (#4191)."
        )
    }

    func testIconTilesUseTheSharedGreyFillNotAccentWashOrStroke() throws {
        // #4024: DocumentThumbnailView/EntityThumbnailView (icon tiles) live in LibraryThumbnailViews.swift.
        let source = try Self.appSource("Views/Library/LibraryThumbnailViews.swift")
        XCTAssertTrue(
            source.contains("LibrarySelectionStyle.fill"),
            "Selected tiles must use the shared grey fill (#4191)."
        )
        XCTAssertFalse(
            source.contains("effectiveSelectedTint.opacity(0.2)"),
            "The #3875 accent wash on tiles must be gone (#4191)."
        )
        XCTAssertFalse(
            source.contains(".stroke(isSelected"),
            "The selected-well accent stroke must be gone — one selection idiom, not two (#4191)."
        )
        // The label still carries the focus/key distinction (accent when key,
        // grey otherwise) via effectiveSelectedTint.
        XCTAssertTrue(source.contains("controlActiveState == .key ? selectedTint : .secondary"))
    }

    func testThumbnailWellHasExplicitPortraitBounds() throws {
        let source = try Self.appSource("Views/Library/LibraryThumbnailViews.swift")

        XCTAssertTrue(source.contains("static let wellWidth: CGFloat = 100"))
        XCTAssertTrue(source.contains("static let wellHeight: CGFloat = wellWidth * 4 / 3"))
        XCTAssertTrue(source.contains(".frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)"))
    }

    func testIconThumbnailsScaleToFitInsideTheFixedWell() throws {
        // #4197 (Daniel 2026-07-28): the whole page must be visible,
        // letterboxed — no cropping a landscape page's sides to fill the
        // portrait well. The well itself keeps its fixed size (#4191 uniform
        // tile density); only the image letterboxes inside it.
        let source = try Self.appSource("Views/Library/LibraryThumbnailViews.swift")

        XCTAssertTrue(
            source.contains(".aspectRatio(contentMode: .fit)"),
            "Icon thumbnails must scale-to-fit, not crop-to-fill (#4197)."
        )
        XCTAssertFalse(
            source.contains(".aspectRatio(contentMode: .fill)"),
            "No image branch may crop-to-fill the well (#4197)."
        )

        // The explicit well frame must survive the .fit switch: without it a
        // landscape image's intrinsic width wins the layout pass and blows
        // past the cell (#789). This assertion is the tripwire for a future
        // "simplification" that drops the frame because .fit "looks fine".
        let imageBranches = source.components(
            separatedBy: "LibraryImageView(documentId: document.id, imageType: .thumbnail)"
        ).dropFirst()
        XCTAssertEqual(imageBranches.count, 2, "Expected the two icon image branches.")
        for branch in imageBranches {
            // Window covers the branch's modifier chain incl. comments; the
            // next branch starts well past it.
            let modifiers = branch.prefix(800)
            XCTAssertTrue(
                modifiers.contains(".frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)"),
                "Each image branch must keep the explicit well frame (#789)."
            )
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("../fichero")
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
