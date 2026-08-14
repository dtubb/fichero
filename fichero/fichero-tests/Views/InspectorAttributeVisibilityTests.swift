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

    // MARK: - Default: Class only

    /// #4422 defaulted to nothing; 2026-08-14 promoted `Class` back in — it is
    /// the datasets system's front door (prototype picker + "Edit Types…"),
    /// and with it hidden Daniel could not find the type editor three times.
    /// Everything ELSE stays off by default.
    @Test("only the Class row is shown by default")
    func onlyClassByDefault() {
        #expect(InspectorAttributeVisibility.visibleAttributes(for: document) == [.documentClass])
        #expect(InspectorAttributeVisibility.showsAnyAttributes(for: document))
        #expect(InspectorAttributeVisibility.defaultVisible == [.documentClass])
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
        let url = try AppSource.root()
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
        #expect(source.contains("InspectorAttributeVisibility.visibleAttributes("))
        // #4481: and that ONE funnel now passes the chooser's answer. Before
        // this, `chosen:` had no caller anywhere in the tree, so the resolver
        // took its `nil` branch forever.
        #expect(source.contains("chosen: choiceStore.chosen(forPrototype: document.prototypeKey)"))
    }

    /// #4481: the issue reported "ten dead cases". The number is right and the
    /// diagnosis needs to be precise, because two different failures look the
    /// same from outside: a case with NO renderer can never appear however it
    /// is configured, whereas a case with a renderer is merely switched off.
    /// Every case here is the second kind — so a case that renders nothing must
    /// fail loudly rather than quietly joining the invisible ten.
    @Test("every attribute has somewhere that renders it")
    func everyAttributeIsRenderedSomewhere() throws {
        let source = try Self.infoTab
        for attribute in InspectorAttribute.allCases {
            #expect(
                source.contains("attribute: .\(attribute.rawValue)"),
                """
                \(attribute.rawValue) has no render site in the Info tab. \
                An attribute that nothing renders cannot be revealed by any \
                choice — either give it a row or delete the case.
                """)
        }
    }

    /// The chooser must be able to offer every case it is possible to render.
    /// A live case the chooser cannot reach is as invisible as one with no row.
    @Test("the chooser can offer every renderable attribute")
    func chooserOffersEveryRenderableAttribute() throws {
        let selectable = Set(InspectorAttributeVisibility.selectable)
        for attribute in InspectorAttribute.allCases {
            #expect(selectable.contains(attribute), "\(attribute) is not offerable")
        }
        let chooser = try Self.appSource(
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+AttributeChooser.swift")
        // Driven off `selectable`, not a hand-written menu that could drift out
        // of step with the enum — a new case is offerable the day it is added.
        #expect(chooser.contains("ForEach(InspectorAttributeVisibility.selectable"))
    }

    /// The affordance cannot be gated on the thing it configures. With the
    /// default empty, a chooser that only appears once something is visible can
    /// never be reached — which is precisely how #4422 became unreachable.
    @Test("the chooser renders even when nothing is visible")
    func chooserIsNotGatedOnVisibility() throws {
        let source = try Self.infoTab
        // Indentation is the assertion: 2e832b24c split the body into three
        // @ViewBuilder groups, and the chooser now sits at the TOP LEVEL of
        // `identitySections` (8 spaces), beside the sections it gates — not
        // inside a condition. One `if` around it and this line indents
        // further and the test fails.
        #expect(source.contains("\n        attributesChooser\n"))
        let chooser = try Self.appSource(
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+AttributeChooser.swift")
        // And it says why the strip is blank, so an unconfigured inspector does
        // not read as a broken one.
        #expect(chooser.contains("No attributes shown."))
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

/// #4481: #4422 made the visible set data, defaulted it to nothing, and never
/// built the chooser — so `chosen:` had no caller and all ten attributes
/// rendered for nobody, forever. This is the store behind that chooser.
///
/// Keyed by PROTOTYPE rather than by document, reusing the seam `#4422` left
/// rather than adding a second visibility mechanism beside it.
@MainActor
struct InspectorAttributeChoiceStoreTests {
    private let document = Document(id: "d1", name: "18590129.pdf")

    /// A private suite per test — these must never touch the user's real
    /// defaults, and one test's choice must not leak into the next.
    private func makeStore(_ name: String = #function) -> InspectorAttributeChoiceStore {
        let suite = "fichero.tests.attributeChoices.\(name)"
        // Cleared through the SUITE's own instance, never `UserDefaults
        // .standard` (#4221): in a test host `.standard` IS the app's own
        // domain, so that call reaches the developer's running app.
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        return InspectorAttributeChoiceStore(defaults: defaults)
    }

    @Test("with no choice made, the prototype inherits the empty default")
    func noChoiceInheritsDefault() {
        let store = makeStore()
        #expect(store.chosen(forPrototype: "diary") == nil)
        #expect(!store.hasChoice(forPrototype: "diary"))
        #expect(
            InspectorAttributeVisibility.visibleAttributes(
                for: document, chosen: store.chosen(forPrototype: "diary")
            ) == InspectorAttributeVisibility.defaultVisible)
    }

    /// The bug in one test: choosing makes an attribute visible. Before #4481
    /// there was no call that could produce a non-empty result.
    @Test("a chosen attribute becomes visible")
    func choosingMakesAnAttributeVisible() {
        let store = makeStore()
        store.toggle(.pageCount, forPrototype: "diary")
        let visible = InspectorAttributeVisibility.visibleAttributes(
            for: document, chosen: store.chosen(forPrototype: "diary"))
        // The default (`Class`) rides along: toggling ADDS to what is shown.
        #expect(visible == [.documentClass, .pageCount])
    }

    @Test("every attribute can be turned on through the chooser")
    func everyAttributeCanBeTurnedOn() {
        let store = makeStore()
        for attribute in InspectorAttributeVisibility.selectable {
            store.setChosen([attribute], forPrototype: "diary")
            #expect(store.isChosen(attribute, forPrototype: "diary"), "\(attribute) cannot be shown")
            let visible = InspectorAttributeVisibility.visibleAttributes(
                for: document, chosen: store.chosen(forPrototype: "diary"))
            #expect(visible == [attribute])
        }
    }

    @Test("toggling twice returns to hidden")
    func togglingTwiceHides() {
        let store = makeStore()
        store.toggle(.state, forPrototype: "diary")
        store.toggle(.state, forPrototype: "diary")
        #expect(!store.isChosen(.state, forPrototype: "diary"))
        // Still a CHOICE, though — "I chose nothing" is not "I chose nothing yet".
        #expect(store.hasChoice(forPrototype: "diary"))
        #expect(store.chosen(forPrototype: "diary") == InspectorAttributeVisibility.defaultVisible)
    }

    /// The point of keying by prototype: a diary page and a legal record show
    /// different sets, each configured once rather than per item.
    @Test("prototypes are configured independently")
    func prototypesAreIndependent() {
        let store = makeStore()
        store.setChosen([.pageCount], forPrototype: "diary")
        store.setChosen([.fileSize], forPrototype: "legal")
        #expect(store.chosen(forPrototype: "diary") == [.pageCount])
        #expect(store.chosen(forPrototype: "legal") == [.fileSize])
        #expect(store.chosen(forPrototype: nil) == nil)
    }

    /// A document with no prototype is not a special case with its own rules —
    /// it is one more bucket, configured the same way.
    @Test("documents with no prototype share one configurable bucket")
    func untypedDocumentsShareABucket() {
        let store = makeStore()
        store.setChosen([.modified], forPrototype: nil)
        #expect(store.chosen(forPrototype: nil) == [.modified])
        // An empty string is the same "no class", not a second bucket.
        #expect(store.chosen(forPrototype: "") == [.modified])
        #expect(store.chosen(forPrototype: "diary") == nil)
    }

    @Test("clearing a choice restores the default rather than showing nothing forever")
    func clearingRestoresTheDefault() {
        let store = makeStore()
        store.setChosen([.state], forPrototype: "diary")
        store.clearChoice(forPrototype: "diary")
        #expect(store.chosen(forPrototype: "diary") == nil)
        #expect(!store.hasChoice(forPrototype: "diary"))
    }

    @Test("a choice survives being reloaded from storage")
    func choiceIsPersisted() {
        let suite = "fichero.tests.attributeChoices.persist"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        InspectorAttributeChoiceStore(defaults: defaults)
            .setChosen([.pageCount, .fileSize], forPrototype: "diary")

        let reloaded = InspectorAttributeChoiceStore(defaults: defaults)
        #expect(reloaded.chosen(forPrototype: "diary") == [.fileSize, .pageCount])
    }

    /// Order follows the declaration however the user ticked the boxes, so the
    /// strip reads the same as it does for anyone else on that prototype.
    @Test("stored order follows the declaration, not the order ticked")
    func storedOrderIsStable() {
        let store = makeStore()
        store.setChosen([.pageCount, .state, .fileSize], forPrototype: "diary")
        #expect(store.chosen(forPrototype: "diary") == [.state, .fileSize, .pageCount])
    }

    /// A stored choice outlives the build that wrote it. A case removed in a
    /// later version must be dropped, not brick the chooser for every document
    /// of that prototype.
    @Test("an unknown stored attribute is dropped, not fatal")
    func unknownStoredAttributeIsDropped() {
        let suite = "fichero.tests.attributeChoices.unknown"
        let defaults = UserDefaults(suiteName: suite)!
        defaults.removePersistentDomain(forName: suite)
        defaults.set(
            ["diary": ["state", "attributeFromTheFuture"]],
            forKey: InspectorAttributeChoiceStore.storageKey)

        let store = InspectorAttributeChoiceStore(defaults: defaults)
        #expect(store.chosen(forPrototype: "diary") == [.state])
    }

    /// Storage internals stay unreachable: the chooser can only ever write
    /// cases of `InspectorAttribute`, which has no case for path or ingest mode.
    @Test("no choice can surface a storage internal")
    func noChoiceSurfacesAStorageInternal() {
        let store = makeStore()
        store.setChosen(InspectorAttribute.allCases, forPrototype: "diary")
        let titles = (store.chosen(forPrototype: "diary") ?? []).map(\.title)
        #expect(!titles.contains("Path"))
        #expect(!titles.contains("Ingest Mode"))
    }
}
