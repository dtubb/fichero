@testable import Fichero
import Testing

/// The Info tab is grouped sections (#5840 part 2): its parts, in order.
struct SourceInfoPartsTests {
    @Test("the Info tab's parts are in the order the page reads them")
    func order() {
        #expect(SourceInfoView.Part.allCases == [
            .making, .folderSync, .iiif, .foundDocuments, .readingAgreement, .info, .whatHasBeenRun, .metadata
        ])
    }
}
