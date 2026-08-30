import XCTest

/// Guardrail for the Mail-style selection treatment (#4191, superseding the
/// #3875 solid-accent fill). The user: selected row = SUBTLE GREY rounded-rect
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
        // Daniel's 2026-08-09 ruling supersedes the flat-grey #4191 pin for
        // LIST ROWS: the fill is the rowFill token (accent focused, grey
        // unfocused — Mail's exact split). The grey lives on as the token's
        // unfocused half and as the icon-tile fill below.
        XCTAssertTrue(
            helpers.contains("LibrarySelectionStyle.rowFill(selected: isSelected, focused: focused)"),
            "List rows must draw the shared rowFill token (2026-08-09 ruling)."
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

    func testFocusSplitLivesInTheSharedContentToken() throws {
        // Daniel's 2026-08-09 ruling supersedes the #4191 label-tint pin:
        // the focus split lives in rowFill/rowContent (accent+white focused,
        // grey+accent unfocused — the native Table look). The tint that feeds
        // the == comparison still flips with focus so rows re-render.
        let displayHelpers = try Self.appSource("Views/Library/ViewModes/LibraryView+DisplayHelpers.swift")
        XCTAssertTrue(
            displayHelpers.contains("isPaneFocused ? .accentColor : .secondary"),
            "selectionTint must keep the focused/unfocused split so .equatable() rows re-render on focus flips."
        )
        let components = try Self.appSource("Views/Library/LibraryViewComponents.swift")
        XCTAssertTrue(
            components.contains("LibrarySelectionStyle.rowContent(selected: isSelected, focused: isPaneFocused)"),
            "The list-row title must take its color from the ONE content token (2026-08-09 ruling)."
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
        // V3 (2026-08-09): the label tint no longer re-gates on
        // controlActiveState — selectedTint applies directly and the focus
        // split lives upstream in the shared tokens. The re-gate coming back
        // is the regression this now watches for.
        XCTAssertFalse(source.contains("controlActiveState == .key ? selectedTint"))
        XCTAssertTrue(source.contains("selectedTint"))
    }

    func testThumbnailWellHasExplicitPortraitBounds() throws {
        let source = try Self.appSource("Views/Library/LibraryThumbnailViews.swift")

        // SQUARE well (Daniel's Finder-screenshot ruling, 2026-08-09) —
        // supersedes the portrait 3:4 pin.
        XCTAssertTrue(source.contains("static let wellWidth: CGFloat = 108"))
        XCTAssertTrue(source.contains("static let wellHeight: CGFloat = wellWidth"))
        XCTAssertTrue(source.contains(".frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)"))
    }

    func testIconThumbnailsScaleToFitInsideTheFixedWell() throws {
        // #4197 (the user 2026-07-28): the whole page must be visible,
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
            // next branch starts well past it. The frame is inset now
            // (wellContentInset, the #125-128 jail margin) but must remain
            // EXPLICIT and wellWidth-derived — dropping it lets a landscape
            // image's intrinsic width win the layout pass (#789).
            // Bounded by the branch's own else-boundary, not a char count —
            // the page-hugging chrome and its comments outgrew every window.
            let modifiers = branch.components(separatedBy: "} else").first ?? ""
            XCTAssertTrue(
                modifiers.contains(".frame(")
                    && modifiers.contains("Self.wellWidth"),
                "Each image branch must keep an explicit wellWidth-derived frame (#789)."
            )
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
