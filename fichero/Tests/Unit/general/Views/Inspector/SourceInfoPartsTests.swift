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

    @Test("a part with nothing to show draws no section")
    func conditionalPartsHideThemselves() {
        func shown(_ part: SourceInfoView.Part, _ type: DocType, path: Bool = false, iiif: Bool = false,
                   metadata: Bool = false) -> Bool {
            SourceInfoView.isShown(part, docType: type, hasPath: path, isIIIFSource: iiif, hasMetadata: metadata)
        }
        // A page: reading agreement, never the folder parts.
        #expect(shown(.readingAgreement, .page))
        #expect(!shown(.folderSync, .page) && !shown(.foundDocuments, .page) && !shown(.iiif, .page))
        // A folder: the folder parts, never reading agreement; IIIF only when it is bound to a source.
        #expect(shown(.foundDocuments, .folder) && !shown(.readingAgreement, .folder))
        #expect(!shown(.folderSync, .folder) && shown(.folderSync, .folder, path: true))
        #expect(!shown(.iiif, .folder) && shown(.iiif, .folder, iiif: true))
        // Metadata only when there is some or a path; the always-parts are always there.
        #expect(!shown(.metadata, .page) && shown(.metadata, .page, metadata: true) && shown(.metadata, .page, path: true))
        #expect(shown(.making, .page) && shown(.info, .folder) && shown(.whatHasBeenRun, .page))
    }
}
