@testable import Fichero
import XCTest

/// Tests for the line-based Markdown block parser behind chat message rendering
/// (#2639). Covers the block types the issue lists.
final class MarkdownBlockTests: XCTestCase {

    func testHeadingLevels() {
        guard case .heading(let level, let content)? = MarkdownBlock.parse("## Title").first else {
            return XCTFail("expected heading")
        }
        XCTAssertEqual(level, 2)
        XCTAssertEqual(content, "Title")
    }

    func testHashWithoutSpaceIsParagraph() {
        guard case .paragraph(let text)? = MarkdownBlock.parse("#nospace").first else {
            return XCTFail("expected paragraph")
        }
        XCTAssertEqual(text, "#nospace")
    }

    func testUnorderedList() {
        guard case .list(let items)? = MarkdownBlock.parse("- one\n- two").first else {
            return XCTFail("expected list")
        }
        XCTAssertEqual(items.map(\.content), ["one", "two"])
        XCTAssertEqual(items.first?.marker, "•")
    }

    func testOrderedList() {
        guard case .list(let items)? = MarkdownBlock.parse("1. first\n2. second").first else {
            return XCTFail("expected list")
        }
        XCTAssertEqual(items.map(\.marker), ["1.", "2."])
        XCTAssertEqual(items.map(\.content), ["first", "second"])
    }

    func testFencedCodeBlockPreservesContentAndDoesNotParseInside() {
        let markdown = "```\n- not a list\n# not a heading\n```"
        guard case .codeBlock(let code)? = MarkdownBlock.parse(markdown).first else {
            return XCTFail("expected code block")
        }
        XCTAssertEqual(code, "- not a list\n# not a heading")
    }

    func testBlockquote() {
        guard case .blockquote(let text)? = MarkdownBlock.parse("> quoted").first else {
            return XCTFail("expected blockquote")
        }
        XCTAssertEqual(text, "quoted")
    }

    func testParagraphJoinsConsecutiveLines() {
        guard case .paragraph(let text)? = MarkdownBlock.parse("hello\nworld").first else {
            return XCTFail("expected paragraph")
        }
        XCTAssertEqual(text, "hello world")
    }

    func testMixedDocumentBlockOrder() {
        let markdown = "# Heading\n\nintro text\n\n- a\n- b\n\n```\ncode\n```"
        let blocks = MarkdownBlock.parse(markdown)
        XCTAssertEqual(blocks.count, 4)
        if case .heading = blocks[0] {} else { XCTFail("0 should be heading") }
        if case .paragraph = blocks[1] {} else { XCTFail("1 should be paragraph") }
        if case .list = blocks[2] {} else { XCTFail("2 should be list") }
        if case .codeBlock = blocks[3] {} else { XCTFail("3 should be code block") }
    }
}
