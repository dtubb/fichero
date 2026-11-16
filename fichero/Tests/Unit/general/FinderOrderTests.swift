@testable import Fichero
import Foundation
import Testing

/// Spec `library.sort.names-in-finder-order` (owner 2026-11-13): names sort the way Finder sorts
/// them, numbers by value.
struct FinderOrderTests {
    private func sorted(_ names: [String]) -> [String] {
        names.sorted { $0.finderOrder($1) }
    }

    @Test func numbersAreComparedByValue() {
        let names = ["101", "2", "100", "10", "1", "9", "11"]
        #expect(sorted(names) == ["1", "2", "9", "10", "11", "100", "101"])
        #expect(sorted(["Hoja 10", "Hoja 2"]) == ["Hoja 2", "Hoja 10"])
        #expect(sorted(["11_Hoja_958", "1_Hoja_958", "2_Hoja_1"]) == ["1_Hoja_958", "2_Hoja_1", "11_Hoja_958"])
    }

    @Test func caseDoesNotDecideTheOrder() {
        #expect(sorted(["Beta", "alpha", "Zed", "apple"]) == ["alpha", "apple", "Beta", "Zed"])
    }

    @Test func namesThatDifferOnlyInCaseHaveAStableOrder() {
        #expect(sorted(["b", "B"]) == sorted(["B", "b"]))
        #expect("a".finderOrder("a") == false)
    }
}
