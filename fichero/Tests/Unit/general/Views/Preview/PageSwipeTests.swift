import CoreGraphics
@testable import Fichero
import Testing

/// A horizontal swipe on a fitted page turns it, as in Photos; a zoomed-in page pans (`preview.ios.swipe-turns-pages`,
/// #6559).
struct PageSwipeTests {
    @Test func aSwipeLeftGoesToTheNextPage() {
        #expect(PageSwipe.step(translation: CGSize(width: -120, height: 10), predictedEnd: .zero, isZoomedIn: false) == 1)
    }

    @Test func aSwipeRightGoesToThePreviousPage() {
        #expect(PageSwipe.step(translation: CGSize(width: 120, height: -5), predictedEnd: .zero, isZoomedIn: false) == -1)
    }

    @Test func aShortFastFlickTurnsThePage() {
        let step = PageSwipe.step(
            translation: CGSize(width: -30, height: 2), predictedEnd: CGSize(width: -200, height: 4), isZoomedIn: false
        )
        #expect(step == 1)
    }

    @Test func aZoomedInPagePansInstead() {
        #expect(PageSwipe.step(translation: CGSize(width: -200, height: 0), predictedEnd: .zero, isZoomedIn: true) == nil)
    }

    @Test func aMostlyVerticalOrShortDragDoesNothing() {
        #expect(PageSwipe.step(translation: CGSize(width: -80, height: 90), predictedEnd: .zero, isZoomedIn: false) == nil)
        #expect(PageSwipe.step(translation: CGSize(width: -20, height: 0), predictedEnd: .zero, isZoomedIn: false) == nil)
    }

    @Test func zoomedInMeansPastTheFittedSize() {
        #expect(!PageSwipe.isZoomedIn(scale: 0.5, fitScale: 0.5))
        #expect(PageSwipe.isZoomedIn(scale: 1.0, fitScale: 0.5))
        #expect(!PageSwipe.isZoomedIn(scale: 1.0, fitScale: nil))
    }
}
