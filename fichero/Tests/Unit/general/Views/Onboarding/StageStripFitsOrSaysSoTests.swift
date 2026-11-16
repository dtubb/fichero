import CoreGraphics
import Testing

@testable import Fichero

/// `source.onboard.stages.output-visible-without-hunting` (#6402): the fit rule and the cue sentence.
struct StageStripFitsOrSaysSoTests {
    @Test func threePicturesFitAWideColumnAtEqualWidths() {
        let fit = StageStripFit.layout(columnWidth: 900, count: 3, minimum: 160)
        #expect(fit == .fits(pictureWidth: 292))
        #expect(fit.cueWords == nil)
    }

    @Test func aNarrowColumnGivesTheCueWithItsPlural() {
        let fit = StageStripFit.layout(columnWidth: 500, count: 3, minimum: 200)
        #expect(fit == .scrolls(pictureWidth: 200, cue: "3 results · scroll →"))
        #expect(fit.pictureWidth == 200)
    }

    @Test func onePictureGivesNoCue() {
        #expect(StageStripFit.layout(columnWidth: 100, count: 1, minimum: 200).cueWords == nil)
        #expect(StageStripFit.cue(count: 1) == "1 result · scroll →")
    }

}
