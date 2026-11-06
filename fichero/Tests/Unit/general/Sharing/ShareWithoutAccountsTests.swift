//
//  ShareWithoutAccountsTests.swift
//  FicheroTests
//
//  sharing.host.share-in-every-mode (#6373, owner 2026-11-06): with Multi-user off a project row's right-click still
//  offers Share…, and the sheet is the project's link (no person), with Turn Sharing On when Sharing is off.
//

@testable import Fichero
import Testing

@MainActor
struct ShareWithoutAccountsTests {
    @Test func aProjectRowOffersShareWithMultiUserOff() {
        #expect(ProjectRowMenuOffers.forProject(isAlwaysThere: false, multiuser: false).share)
        #expect(!ProjectRowMenuOffers.forProject(isAlwaysThere: true, multiuser: false).share)
    }

    @Test func withMultiUserOffAProjectIsSharedByLinkNotToAPerson() {
        #expect(!ShareLibrarySheet.sharesWithPeople(multiuser: false, folder: false))
        #expect(ShareLibrarySheet.sharesWithPeople(multiuser: true, folder: false))
        #expect(ShareLibrarySheet.sharesWithPeople(multiuser: false, folder: true))
        #expect(ShareLibrarySheet.noAccountsNote.contains("Settings › Sharing"))
    }
}
