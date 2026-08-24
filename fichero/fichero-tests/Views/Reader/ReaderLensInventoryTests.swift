//
//  ReaderLensInventoryTests.swift
//  FicheroTests
//
//  R3 (Daniel, 2026-08-23): the reader's tabs fold into the pane head's
//  two-level selector, and the lens list is an INVENTORY of the surfaces that
//  are actually built. His complaint that named the defect: the reader "lost
//  some things like node graph and maps — they're in the menu bar." Graph and
//  Map existed and rendered; only the View menu could reach them.
//

@testable import Fichero
import Foundation
import Testing

struct ReaderLensInventoryTests {

    @Test("every lens maps to a surface that exists")
    func lensesAreAnInventory() {
        // A lens is a promise that something renders. Page and Notes are whole
        // tabs; the other seven are knowledge sub-modes, and each must name one.
        for lens in ReaderLens.allCases {
            switch lens {
            case .page, .notes:
                #expect(lens.representation == nil)
            default:
                #expect(lens.representation != nil, "\(lens.title) names no surface")
            }
        }
    }

    @Test("the surfaces that were menu-bar-only are lenses now")
    func graphAndMapAreReachable() {
        let titles = ReaderLens.allCases.map(\.title)
        #expect(titles.contains("Node Graph"))
        #expect(titles.contains("Map"))
        // And the rest of the built inventory, so a future edit cannot quietly
        // drop one back to menu-only. Transcript is NOT here (2026-08-23):
        // Page IS the multi-page transcript, and the separate row landed on
        // Entities via the knowledge surface's stale-value clamp.
        for expected in ["Content", "Statements", "Entities", "Claims", "Timeline", "Notes"] {
            #expect(titles.contains(expected), "\(expected) fell out of the lens list")
        }
        #expect(!titles.contains("Transcript"), "the duplicate Transcript lens came back")
    }

    @Test("Translation is absent, because it does not exist")
    func noLensGoesNowhere() {
        // Dead-simple-UX: features are ON or OFF. A lens row for an unbuilt
        // surface is the menu lying, so new lenses join when their surfaces do.
        #expect(!ReaderLens.allCases.map(\.title).contains("Translation"))
    }

    @Test("every knowledge lens names a DISTINCT sub-mode")
    func lensesDoNotCollide() {
        let representations = ReaderLens.allCases.compactMap(\.representation)
        #expect(Set(representations).count == representations.count,
                "two lenses point at the same surface")
        // Every knowledge sub-mode the app implements is reachable — this is
        // the assertion that fails when a new KGSurfaceTab is added without a
        // lens, which is exactly how Graph and Map became menu-only.
        #expect(Set(representations) == Set(KGSurfaceTab.allCases),
                "a built knowledge surface has no lens — it is menu-bar-only again")
    }

    @Test("lens ↔ (tab, representation) round-trips")
    func lensRoundTrips() {
        // The head, the menu bar and restored scene state all resolve through
        // this, so a lens that does not survive the round trip would show one
        // thing and select another.
        for lens in ReaderLens.allCases {
            let resolved = ReaderLens.lens(
                for: lens.tab,
                representation: lens.representation ?? .entities
            )
            #expect(resolved == lens, "\(lens.title) did not round-trip")
        }
    }

    @Test("a knowledge tab with an unknown sub-mode falls back rather than crashing")
    func unknownRepresentationFallsBack() {
        #expect(ReaderLens.lens(for: .page, representation: .map) == .page)
        #expect(ReaderLens.lens(for: .notes, representation: .graph) == .notes)
    }
}

// MARK: - The head, and the one binding rendered twice

struct PaneHeadWiringGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }

    private func code(at relativePath: String) throws -> String {
        Self.code(of: try appSource(relativePath))
    }

    @Test("the head floats over the content — no opaque bar (R7)")
    func headFloats() throws {
        let head = try code(at: "Views/Shell/PaneHead/PaneHead.swift")
        // Native Tahoe glass since 2026-08-23 (S1): the opaque material read
        // as "not standard"; the float is the glass capsule itself.
        #expect(head.contains(".glassEffect(.regular, in: Capsule())"))
        let reader = try code(at: "Views/Reader/Page/ReadingPaneView.swift")
        // safeAreaInset since 2026-08-23: the first row starts BELOW the
        // head while scrolled content still passes under the glass — and the
        // inset height is CONSTANT (see PaneHeadMetrics.barHeight, the 15s
        // lazy-list re-layout stall).
        #expect(reader.contains(".safeAreaInset(edge: .top, spacing: 0) { paneHead }"))
    }

    @Test("the reader's tab bar is gone — those three are lenses now")
    func tabBarRetired() throws {
        let reader = try code(at: "Views/Reader/Page/ReadingPaneView.swift")
        #expect(!reader.contains("SurfaceTabBar(tabs: ReaderTab.allCases"),
                "the reader still carries its own tab bar beside the head")
        #expect(reader.contains("PaneKindSelector("))
    }

    @Test("head and menu bar read ONE published lens")
    func oneBindingRenderedTwice() throws {
        // The defect this whole audit has been unwinding: two switches for one
        // choice. The menu section reads the publication; it owns no state.
        let reader = try code(at: "Views/Reader/Page/ReadingPaneView.swift")
        #expect(reader.contains("focusedSceneValue(\\.readerLens"))

        let section = try code(at: "App/Menus/ReaderLensSection.swift")
        #expect(section.contains("@FocusedValue(\\.readerLens)"))
        #expect(section.contains("readerLens?.set(lens)"))
        #expect(!section.contains("@State"), "the menu section grew its own copy of the selection")
        #expect(section.contains(".disabled(readerLens == nil)"))

        // Equatable on the VALUE only — comparing the setter republishes every
        // body pass (the ×31 fault).
        let values = try code(at: "App/Menus/FocusedCommandButtons+FocusedValues.swift")
        let tail = try #require(values.components(separatedBy: "struct FocusedReaderLens").last)
        let body = try #require(tail.components(separatedBy: "\nstruct ").first)
        #expect(body.contains("lhs.value == rhs.value"))
        #expect(!body.contains("lhs.set"))
    }

    @Test("the kind menu offers no change it cannot make")
    func kindIsNotStubbed() throws {
        // Only the Reader adopts the head in step 1, so the kind renders as a
        // label. A menu of pane kinds that cannot switch would be R3's control
        // lying about what it does.
        let selector = try code(at: "Views/Shell/PaneHead/PaneKindSelector.swift")
        #expect(selector.contains("Label(kindTitle, systemImage: kindIcon)"))
        #expect(!selector.contains("Picker(\"Kind\""))
    }

    @Test("the crumb is FULL ancestry, through the walk that already exists")
    func crumbsAreFullAncestry() throws {
        // R1: the title line IS the breadcrumb — "Marshall Diaries v4 › Inbox ›
        // 1933", not "Reader". Daniel, 2026-08-23: full ancestry, in scope now.
        let reader = try code(at: "Views/Reader/Page/ReadingPaneView.swift")
        #expect(reader.contains("libraryPathCrumbs("),
                "the reader walks ancestors itself — two walks disagree eventually")
        #expect(reader.contains("documentStore.resolveDocument($0)"))
        // The library is the root crumb: a path starting at a folder does not
        // say WHICH library's Inbox you are in.
        #expect(reader.contains("private var libraryName: String?"))
    }

    @Test("the crumb capsule truncates from the LEADING edge")
    func crumbsTruncateFromTheHead() throws {
        // A deep path's tail identifies it; its head is inferable. Proxy-icon
        // collapse is a later slice, so truncation is what keeps a long path
        // readable until then.
        let head = try code(at: "Views/Shell/PaneHead/PaneHead.swift")
        #expect(head.contains(".truncationMode(.head)"))
        #expect(head.contains(".lineLimit(1)"))
    }
}