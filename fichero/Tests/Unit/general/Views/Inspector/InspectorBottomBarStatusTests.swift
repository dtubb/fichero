//
//  InspectorBottomBarStatusTests.swift
//  FicheroTests
//
//  panes.chrome.bars-do-not-name-the-selection (owner 2026-11-13): an inspector bar draws no empty status line, and the
//  Content/Info/Outline/Order bars no longer pass the selection's name. See docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import SwiftUI
import Testing

struct InspectorBottomBarStatusTests {
    typealias Bar = InspectorBottomMiniToolbar<EmptyView>

    @Test("an empty status draws nothing; a count still shows")
    func emptyStatusIsNotDrawn() {
        #expect(!Bar.showsStatus(""))
        #expect(!Bar.showsStatus("  "))
        #expect(Bar.showsStatus("3 notes"))
    }
}
