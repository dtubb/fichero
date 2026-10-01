import Testing

@testable import Fichero

/// The pure half of page import: what the report says. No engine, no window, no
/// build destination — which is why `PageImportRunner.Text` holds no UI.
@Suite("Page import text")
struct PageImportTextTests {
    @Test("the format that was RECOGNISED is named, not the one the file's name suggests")
    func recognisedFormatIsNamed() {
        let line = PageImportRunner.Text.recognisedLine(fileName: "notes.txt", recognisedFormat: "pagexml")
        #expect(line.contains("PAGE XML"))
        #expect(line.contains("notes.txt"))
        // A .txt that is really PAGE XML must SAY the contents decided.
        #expect(line.contains(".txt"))
        #expect(line.contains("the contents decide"))
    }

    @Test("a file whose extension agrees with its contents says nothing extra")
    func agreeingExtensionIsQuiet() {
        let line = PageImportRunner.Text.recognisedLine(fileName: "folio.page.xml", recognisedFormat: "pagexml")
        #expect(line.contains("PAGE XML"))
        #expect(!line.contains("the contents decide"))
    }

    @Test("a file with no extension at all is noticed")
    func noExtensionIsNoticed() {
        let line = PageImportRunner.Text.recognisedLine(fileName: "export", recognisedFormat: "alto")
        #expect(line.contains("no extension"))
    }

    @Test("format names are the ones a person knows")
    func formatTitles() {
        #expect(PageImportRunner.Text.formatTitle("pagexml") == "PAGE XML")
        #expect(PageImportRunner.Text.formatTitle("alto") == "ALTO")
        #expect(PageImportRunner.Text.formatTitle("tei") == "TEI")
        #expect(PageImportRunner.Text.formatTitle("hocr") == "hOCR")
        #expect(PageImportRunner.Text.formatTitle("yolo") == "YOLO")
        #expect(PageImportRunner.Text.formatTitle("newformat") == "newformat")
    }

    @Test("repaired shapes are a warning that leads the report, not a footnote")
    func geometryProblemsLeadTheReport() {
        let report = PageImportRunner.Text.report(
            fileName: "folio.page.xml", recognisedFormat: "pagexml",
            segments: 812, readings: 806, orderEntries: 24, geometryProblems: 40
        )
        let warningRange = report.range(of: "40 segments have a shape")
        let readRange = report.range(of: "Read folio.page.xml")
        #expect(warningRange != nil)
        #expect(readRange != nil)
        if let warningRange, let readRange {
            #expect(warningRange.lowerBound < readRange.lowerBound)
        }
    }

    @Test("no repaired shapes means no warning at all")
    func noWarningWhenClean() {
        #expect(PageImportRunner.Text.geometryWarning(count: 0) == nil)
        let report = PageImportRunner.Text.report(
            fileName: "a.xml", recognisedFormat: "tei", segments: 1, readings: 1, orderEntries: 0, geometryProblems: 0
        )
        #expect(!report.contains("Worth a look"))
    }

    @Test("one repaired shape is singular")
    func oneRepairedShape() {
        let warning = PageImportRunner.Text.geometryWarning(count: 1)
        #expect(warning?.contains("1 segment has") == true)
        #expect(warning?.contains("was repaired") == true)
    }

    @Test("counts are singular where they are one")
    func summaryCounts() {
        let one = PageImportRunner.Text.summary(segments: 1, readings: 1, orderEntries: 1)
        #expect(one.contains("1 segment,"))
        #expect(one.contains("1 reading,"))
        #expect(one.contains("1 reading-order entry"))
        let many = PageImportRunner.Text.summary(segments: 812, readings: 806, orderEntries: 24)
        #expect(many.contains("812 segments"))
        #expect(many.contains("806 readings"))
        #expect(many.contains("24 reading-order entries"))
    }

    @Test("the report says the import is not the working pass")
    func notTheWorkingPass() {
        let report = PageImportRunner.Text.report(
            fileName: "a.xml", recognisedFormat: "tei", segments: 3, readings: 3, orderEntries: 3, geometryProblems: 0
        )
        #expect(report.contains("not the working pass"))
        #expect(report.contains("nothing already on the page was changed"))
    }

    /// #5308: a 24-page TEI edition imported onto one page brings in page 1. The engine names the
    /// 23 pages it left out; the report used to say nothing, so the person saw a plain success.
    @Test("pages a multi-page file left out lead the report, named as the engine names them")
    func pagesLeftOutLeadTheReport() {
        let report = PageImportRunner.Text.report(
            fileName: "kouigenji-01.tei.xml", recognisedFormat: "tei",
            segments: 20, readings: 20, orderEntries: 20, geometryProblems: 0,
            pagesInFile: 3, pagesLeftOut: ["page 2 (n=2)", "page 3 (n=3)"]
        )
        let warning = report.range(of: "1 of its 3 pages")
        let read = report.range(of: "Read kouigenji-01.tei.xml")
        #expect(warning != nil)
        #expect(report.contains("page 2 (n=2)"))
        #expect(report.contains("page 3 (n=3)"))
        if let warning, let read { #expect(warning.lowerBound < read.lowerBound) }
    }

    @Test("a one-page file says nothing about pages")
    func onePageSaysNothing() {
        #expect(PageImportRunner.Text.pagesLeftOutWarning(pagesInFile: 1, leftOut: []) == nil)
    }

    @Test("the pass a 409 names is found in the engine's own sentence")
    func passIdIsExtracted() {
        let detail = "'folio.xml' is already on this document as pass 0123456789abcdef0123456789abcdef (same content, sha256 abc…). Nothing was written."
        #expect(PageImportRunner.Text.passID(fromDetail: detail) == "0123456789abcdef0123456789abcdef")
        #expect(PageImportRunner.Text.passID(fromDetail: "something else") == nil)
    }

    @Test("the same bytes twice is an ANSWER naming the pass, not a failure")
    func alreadyImportedIsAnAnswer() {
        let detail = "'folio.xml' is already on this document as pass 0123456789abcdef0123456789abcdef (same content). Nothing was written."
        let answer = PageImportRunner.Text.alreadyImported(fileName: "folio.xml", detail: detail)
        #expect(answer.title == "Already imported")
        #expect(answer.body.contains("0123456789abcdef0123456789abcdef"))
        #expect(answer.body.contains("Nothing was written"))
        #expect(!answer.title.lowercased().contains("fail"))
        #expect(!answer.title.lowercased().contains("error"))
    }

    @Test("a refusal that names no pass still answers, in the engine's words")
    func alreadyImportedWithoutAPass() {
        let answer = PageImportRunner.Text.alreadyImported(fileName: "f.xml", detail: "already there")
        #expect(answer.body.contains("already there"))
        #expect(answer.body.contains("f.xml"))
    }
}
