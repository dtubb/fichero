import Testing

@testable import Fichero

/// The pure half of page export: the filename it suggests and the report it
/// shows. No engine, no window, no build destination — which is the point of
/// keeping `PageExportRunner.Text` free of UI.
@Suite("Page export text")
struct PageExportTextTests {
    @Test("a filename names WHICH xml it is, not just that it is xml")
    func filenameCarriesTheFormat() {
        #expect(PageExportRunner.Text.filename(forDocumentNamed: "1933 Diary", format: .pagexml)
            == "1933 Diary.page.xml")
        #expect(PageExportRunner.Text.filename(forDocumentNamed: "1933 Diary", format: .alto)
            == "1933 Diary.alto.xml")
        #expect(PageExportRunner.Text.filename(forDocumentNamed: "1933 Diary", format: .tei)
            == "1933 Diary.tei.xml")
    }

    @Test("a slash in a document name cannot promise a file in a missing directory")
    func filenameIsSanitised() {
        let name = PageExportRunner.Text.filename(forDocumentNamed: "1933/34", format: .pagexml)
        #expect(!name.contains("/"))
        #expect(name.hasSuffix(".page.xml"))
    }

    @Test("the summary names the pass, the order and the reading kind")
    func summaryNamesTheChoices() {
        let line = PageExportRunner.Text.summary(
            format: .tei, passName: "Kraken 4.3", passBasis: "working pass",
            orderName: "as-written", readingKind: "transcription", segmentCount: 24
        )
        #expect(line.contains("TEI"))
        #expect(line.contains("Kraken 4.3"))
        #expect(line.contains("working pass"))
        #expect(line.contains("as-written"))
        #expect(line.contains("transcription"))
        #expect(line.contains("24 segments"))
    }

    @Test("one segment is not pluralised")
    func summaryCountsOne() {
        let line = PageExportRunner.Text.summary(
            format: .alto, passName: nil, passBasis: nil,
            orderName: nil, readingKind: nil, segmentCount: 1
        )
        #expect(line.contains("1 segment"))
        #expect(!line.contains("1 segments"))
    }

    @Test("nothing lost is SAID, not shown as an empty list")
    func nothingLostIsStated() {
        // An empty list reads as "no report". This is a report, and its
        // finding is that there was nothing to report.
        let text = PageExportRunner.Text.losses([])
        #expect(text.contains("Nothing was lost"))
        #expect(!text.contains("Not carried"))
    }

    @Test("every loss is named, with its count and its reason")
    func lossesAreNamedWithReasons() {
        let text = PageExportRunner.Text.losses([
            (what: "named reading orders", why: "PAGE XML holds one per page", count: 2),
            (what: "which reading counts", why: "TextEquiv indexes but cannot say", count: 1),
        ])
        #expect(text.contains("named reading orders ×2"))
        #expect(text.contains("PAGE XML holds one per page"))
        // A single loss is not given a count: "×1" is noise a reader has to
        // decode, and the line already names one thing.
        #expect(text.contains("which reading counts —"))
        #expect(!text.contains("which reading counts ×1"))
    }
}
