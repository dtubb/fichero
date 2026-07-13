import SwiftUI
import Testing

@testable import Fichero

/// Reader / Editor font-scale math (#3681 / #3682). The editor surfaces scale the
/// *semantic* base of the style they were designed with — never a hardcoded size —
/// so a `.caption` editor stays smaller than a `.body` one at every user scale.
@MainActor
struct ViewSettingsFontScaleTests {
    private typealias FontScale = ViewSettings.FontScale

    @Test func clampsOutOfRangeScales() {
        #expect(FontScale.clamped(0.1) == FontScale.range.lowerBound)
        #expect(FontScale.clamped(9.0) == FontScale.range.upperBound)
        #expect(FontScale.clamped(1.3) == 1.3)
        // A corrupted `0` default must not read as "tiny" — it clamps to the floor.
        #expect(FontScale.clamped(0) == 0.8)
    }

    @Test func readerAndEditorKeysAreDistinct() {
        #expect(FontScale.readerKey != FontScale.editorKey)
    }

    @Test func percentLabelRounds() {
        #expect(FontScale.percentLabel(1.0) == "100%")
        #expect(FontScale.percentLabel(1.25) == "125%")
        #expect(FontScale.percentLabel(0.8) == "80%")
    }

    @Test func editorSizeScalesTheSemanticBase() {
        let base = FontScale.semanticSize(.body)
        #expect(FontScale.editorSize(.body, scale: 1.0) == base)
        #expect(FontScale.editorSize(.body, scale: 2.0) == base * 2)
        #expect(FontScale.editorBodySize(scale: 1.5) == base * 1.5)
    }

    @Test func editorSizeClampsBeforeScaling() {
        let base = FontScale.semanticSize(.body)
        #expect(FontScale.editorSize(.body, scale: 99) == base * FontScale.range.upperBound)
        #expect(FontScale.editorSize(.body, scale: 0) == base * FontScale.range.lowerBound)
    }

    /// The adoption sweep passes each surface's own style; scaling must preserve
    /// their relative order (caption < callout < body), not flatten to one size.
    @Test func semanticStylesKeepTheirRelativeOrder() {
        let scale = 1.4
        let caption = FontScale.editorSize(.caption, scale: scale)
        let callout = FontScale.editorSize(.callout, scale: scale)
        let body = FontScale.editorSize(.body, scale: scale)
        #expect(caption < callout)
        #expect(callout <= body)
        #expect(caption < body)
    }

    @Test func unmappedStyleFallsBackToBody() {
        #expect(FontScale.semanticSize(.title) > FontScale.semanticSize(.body))
        #expect(FontScale.semanticSize(.caption2) < FontScale.semanticSize(.body))
    }
}
