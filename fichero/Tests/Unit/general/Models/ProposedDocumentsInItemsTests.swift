@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Organise review in Items (`finddocs.review.items`, #5550), written from the spec: after a run, a folder's Items
/// list shows each document still proposed as a proposal, never as a document, holding its pages; a page in no
/// proposal stays loose; the person answers by the row's menu, Accept and Reject for everything selected, and for
/// one document the adjustments that change which pages belong. Also Set Up's Organise page
/// (`finddocs.review.setup-page`): what it does, and the grouping a try on the samples proposes.
@MainActor
struct ProposedDocumentsInItemsTests {
    let folder = Document(id: "folder", docType: .folder, name: "1948 Sentencias")

    private func page(_ id: String) -> Document {
        Document(id: id, parentId: "folder", docType: .page, name: id)
    }

    private func waiting(_ index: Int, _ pages: [String], first: Int, previousOpen: Bool = false,
                         nextOpen: Bool = false) -> FoundDocumentsStore.Waiting {
        FoundDocumentsStore.Waiting(
            proposalId: "p1",
            document: .init(index: index, name: "Sentencia \(index + 1)", pageIds: pages, firstPosition: first,
                            lastPosition: first + pages.count - 1, kind: "Sentencia", confidence: 0.82),
            previousIsOpen: previousOpen, nextIsOpen: nextOpen
        )
    }

    private var rows: [LibraryOutlineNode] {
        ["a", "b", "c", "d", "e"].map { LibraryOutlineNode.document(page($0), children: nil) }
    }

    @Test("a proposal stands where its first page stood and holds its pages; a page in none stays loose")
    func proposalsReplaceTheirPages() {
        let shown = LibraryOutlineNode.withProposals(
            rows, waiting: [waiting(0, ["b", "c"], first: 1), waiting(1, ["e"], first: 4)], folder: folder
        )
        #expect(shown.map(\.id) == ["a", "proposed:p1#0", "d", "proposed:p1#1"])
        let first = shown[1]
        #expect(first.children?.map(\.id) == ["folder:page:b", "folder:page:c"], "its pages, as page rows")
        #expect(first.canExpand, "it discloses its pages")
        if case .proposedDocument(let item) = first.kind {
            #expect(item.document.name == "Sentencia 1")
        } else {
            Issue.record("a proposal is never shown as a document row")
        }
        #expect(first.document.id == "folder", "it names no stored document: its document is the folder")
    }

    @Test("with nothing waiting the rows are the folder's own; a proposal none of whose pages is listed is not shown")
    func nothingWaitingChangesNothing() {
        #expect(LibraryOutlineNode.withProposals(rows, waiting: [], folder: folder).map(\.id) == rows.map(\.id))
        let filtered = LibraryOutlineNode.withProposals(rows, waiting: [waiting(0, ["x", "y"], first: 7)], folder: folder)
        #expect(filtered.map(\.id) == rows.map(\.id))
    }

    @Test("the selection names the proposals it holds, by their row or one of their pages")
    func selectionNamesProposals() throws {
        let items = [waiting(0, ["b", "c"], first: 1, nextOpen: true), waiting(1, ["e"], first: 4)]
        let both = try #require(LibraryOutlineNode.proposalTarget(
            for: ["proposed:p1#1", "folder:page:b", "a"], waiting: items, folderId: "folder"
        ))
        #expect(both.documents.map(\.id) == ["p1#0", "p1#1"], "in page order; a loose page names none")
        #expect(both.pageId == nil, "a page only when one page row is selected")

        let onePage = try #require(LibraryOutlineNode.proposalTarget(for: ["folder:page:c"], waiting: items,
                                                                      folderId: "folder"))
        #expect(onePage.pageId == "c")
        #expect(LibraryOutlineNode.proposalTarget(for: ["a"], waiting: items, folderId: "folder") == nil,
                "a loose page's menu is the ordinary one")
    }

    @Test("the menu answers everything selected, and for one document offers what changes its pages")
    func menuOffers() {
        let middle = waiting(1, ["c", "d", "e"], first: 2, previousOpen: true, nextOpen: true)
        func titles(_ ids: [FoundDocumentsStore.Waiting], page: String?) -> [String] {
            ProposedDocumentsMenu.offers(for: .init(documents: ids, pageId: page)).map(\.title)
        }
        #expect(titles([middle, waiting(2, ["f"], first: 5)], page: nil) == ["Accept 2 Documents", "Reject 2 Documents"])
        #expect(titles([middle], page: nil) == ["Accept Document", "Reject Document", "Join with Next Document"])
        #expect(titles([middle], page: "c")
                == ["Accept Document", "Reject Document", "Move Page to Previous Document", "Join with Next Document"],
                "its first page can move back, never split off before itself")
        #expect(titles([middle], page: "d") == ["Accept Document", "Reject Document", "Split Here", "Join with Next Document"])
        #expect(titles([middle], page: "e").contains("Move Page to Next Document"))
        let alone = waiting(0, ["a"], first: 0, previousOpen: true, nextOpen: true)
        #expect(!titles([alone], page: "a").contains { $0.hasPrefix("Move Page") }, "a move never empties a document")
        let lastAnswered = waiting(0, ["a", "b"], first: 0)
        #expect(!titles([lastAnswered], page: "b").contains("Move Page to Next Document"),
                "a neighbour already answered takes no page")
    }

    @Test("a proposed row reads as a proposal: its pages, kind and how sure")
    func proposedRowWords() {
        let document = waiting(0, ["b", "c", "d"], first: 2).document
        #expect(ProposedDocumentNameCell.detail(of: document) == "Pages 3–5 · Sentencia · 82% sure")
    }

    @Test("Set Up's Organise page says how its results reach the project; other stages need no note")
    func organisePageSaysHowItAnswers() throws {
        let note = try #require(SetupStagePage.howItAnswers("organise"))
        #expect(note.contains("Proposed") && note.contains("Items") && note.contains("⌘Z"))
        #expect(!note.contains("95"), "the level is the project's, never written into the app")
        #expect(SetupStagePage.howItAnswers("names") == nil)
    }

    @Test("a try on the samples that groups them shows each proposed document and its pages")
    func tryShowsTheGrouping() throws {
        let json = """
        {"state":"done","documents":[{"name":"Sentencia","page_ids":["s1","s2"],"kind":"Sentencia",
         "confidence":0.9,"reasons":["VISTOS"]}]}
        """
        let result = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
        let document = try #require(result.documents?.first)
        #expect(document.pageIds == ["s1", "s2"])
        #expect(SetupStageTryResult.detail(of: document) == "Sentencia · 90% sure")
        let plain = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(#"{"state":"done"}"#.utf8))
        #expect(plain.documents == nil, "a stage that groups nothing shows no grouping")
    }
}
