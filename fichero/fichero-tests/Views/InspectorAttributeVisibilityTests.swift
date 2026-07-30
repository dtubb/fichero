@testable import Fichero
import Foundation
import Testing

/// #4422: the inspector's Attributes strip showed internal bookkeeping by
/// default — `Ingest COPY`, `Path files/fi/ca408d0…oad_c84fgjke.pdf`, `Kind`,
/// `Status`, filesystem `Created`/`Modified`. Of the seven rows shown by
/// default, one was useful and six described how the app filed the bytes.
///
/// Two changes, and the second matters more than the first: the default is now
/// nothing, and the visible set is DATA rather than a hardcoded strip — so
/// Tinderbox-style per-item/per-prototype visibility arrives as a change to the
/// resolver instead of a rewrite.
struct InspectorAttributeVisibilityTests {
    private let document = Document(id: "d1", name: "18590129.pdf")

    // MARK: - Default: nothing

    @Test("no attributes are shown by default")
    func noAttributesByDefault() {
        #expect(InspectorAttributeVisibility.visibleAttributes(for: document).isEmpty)
        #expect(!InspectorAttributeVisibility.showsAnyAttributes(for: document))
        #expect(InspectorAttributeVisibility.defaultVisible.isEmpty)
    }

    /// Every one of the six rows Daniel called out is absent by default.
    @Test("the rows that used to fill the strip are all absent")
    func thePreviouslyDefaultRowsAreAbsent() {
        let visible = InspectorAttributeVisibility.visibleAttributes(for: document)
        for attribute in [InspectorAttribute.state, .kind, .created, .modified, .fileType, .format] {
            #expect(!visible.contains(attribute), "\(attribute) must not be shown by default")
        }
    }

    // MARK: - Storage internals are not offerable AT ALL

    /// The strongest form of the requirement: ingest mode and storage path are
    /// not hidden by default, they are not cases. There is no configuration —
    /// no prototype, no user choice — in which the app shows someone their
    /// internal storage path. Modelling them as "available but off" would leave
    /// a switch that must never be flipped.
    @Test("ingest mode and storage path are not attributes at all")
    func storageInternalsAreNotAttributes() {
        let names = InspectorAttribute.allCases.map { $0.rawValue.lowercased() }
        for internalName in ["ingest", "ingestmode", "path", "storagepath", "id", "documentid"] {
            #expect(!names.contains(internalName), "\(internalName) must not be an attribute")
        }
        let titles = InspectorAttribute.allCases.map { $0.title.lowercased() }
        #expect(!titles.contains("path"))
        #expect(!titles.contains("ingest mode"))
    }

    /// And they cannot arrive through the selectable set either.
    @Test("nothing selectable is a storage internal")
    func nothingSelectableIsAStorageInternal() {
        #expect(InspectorAttributeVisibility.selectable.count == InspectorAttribute.allCases.count)
        for attribute in InspectorAttributeVisibility.selectable {
            #expect(attribute.title != "Path")
            #expect(attribute.title != "Ingest Mode")
        }
    }

    // MARK: - The set is data, so prototypes are not foreclosed

    /// The point of the resolver: an explicit choice is honoured. This is the
    /// call a per-prototype resolver will make later.
    @Test("an explicit choice is honoured")
    func explicitChoiceIsHonoured() {
        let visible = InspectorAttributeVisibility.visibleAttributes(
            for: document,
            chosen: [.pageCount, .state]
        )
        #expect(visible.contains(.state))
        #expect(visible.contains(.pageCount))
        #expect(!visible.contains(.kind))
        #expect(InspectorAttributeVisibility.showsAnyAttributes(for: document, chosen: [.state]))
    }

    /// Order follows the declaration, not the caller, so the strip reads the
    /// same however a prototype assembled its list.
    @Test("visible order is stable regardless of how the choice was assembled")
    func orderIsStable() {
        let forwards = InspectorAttributeVisibility.visibleAttributes(
            for: document, chosen: [.state, .kind, .pageCount]
        )
        let backwards = InspectorAttributeVisibility.visibleAttributes(
            for: document, chosen: [.pageCount, .kind, .state]
        )
        #expect(forwards == backwards)
    }

    @Test("an empty explicit choice shows nothing")
    func emptyChoiceShowsNothing() {
        #expect(InspectorAttributeVisibility.visibleAttributes(for: document, chosen: []).isEmpty)
        #expect(!InspectorAttributeVisibility.showsAnyAttributes(for: document, chosen: []))
    }

    @Test("every attribute has a title, and titles are unique")
    func everyAttributeHasAUniqueTitle() {
        var seen = Set<String>()
        for attribute in InspectorAttribute.allCases {
            #expect(!attribute.title.isEmpty, "\(attribute)")
            #expect(seen.insert(attribute.title).inserted, "duplicate title: \(attribute.title)")
        }
    }

    // MARK: - Structural

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static var infoTab: String {
        get throws { try appSource("Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift") }
    }

    /// The storage-internal rows are deleted from the view, not merely gated —
    /// a gated row is one config change away from returning.
    @Test("the ingest and path rows are gone from the view")
    func storageRowsAreGoneFromTheView() throws {
        let source = try Self.infoTab
        // Anchored on the ROW form, not the bare words: the comment left where
        // those rows used to be names them deliberately, so the next reader
        // knows they were removed rather than never existing.
        #expect(!source.contains("name: \"Ingest Mode\""))
        #expect(!source.contains("attribute: .ingestMode"))
        #expect(!source.contains("attribute: .path"))
        #expect(!source.contains("document.ingestMode"))
    }

    /// Enforced at ONE funnel rather than fifteen `if`s that could drift.
    @Test("every attribute row passes through one visibility gate")
    func oneGateForEveryRow() throws {
        let source = try Self.infoTab
        #expect(source.contains("if visibleAttributes.contains(attribute)"))
        #expect(source.contains("InspectorAttributeVisibility.visibleAttributes(for: document)"))
    }

    /// With every row gated off, a section that is nothing but attribute rows
    /// must not leave a bare heading above empty space — that would be worse
    /// than the strip it replaced.
    @Test("attribute-only section headings follow their rows")
    func sectionHeadingsFollowTheirRows() throws {
        let source = try Self.infoTab
        #expect(source.contains("func attributeSection<Content: View>"))
        #expect(source.contains("attributes.contains(where: visibleAttributes.contains)"))
        for section in ["Status", "Class", "File", "Content"] {
            #expect(
                source.contains("attributeSection(\"\(section)\""),
                "\(section) is attribute-only and must follow its rows")
        }
        // Sections that carry real content keep rendering unconditionally.
        #expect(source.contains("infoSection(\"Related Claims\")"))
        #expect(source.contains("infoSection(\"Workflow History\")"))
    }
}
