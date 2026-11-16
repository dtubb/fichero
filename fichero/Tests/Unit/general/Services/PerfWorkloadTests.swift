#if os(macOS)
import Foundation
import Testing

@testable import Fichero

@Suite("Perf workload selection")
struct PerfWorkloadTests {
    @Test("FICHERO_PERF_WORKLOAD selects W6-W10 under --uitesting")
    func selectsEachApplicationWorkload() {
        for id in ["w6", "w7", "w8", "w9", "w10"] {
            let picked = PerfWorkload.selected(arguments: ["Fichero", "--uitesting"], environment: ["FICHERO_PERF_WORKLOAD": id])
            #expect(picked?.rawValue == id)
            #expect(picked?.phases.isEmpty == false)
            #expect((picked?.repeats ?? 0) >= 1)
        }
        #expect(PerfWorkload.allCases.count == 5)
    }

    @Test("without --uitesting, or with an unknown id, nothing is selected")
    func refusesOutsideTheTestHook() {
        #expect(PerfWorkload.selected(arguments: ["Fichero"], environment: ["FICHERO_PERF_WORKLOAD": "w6"]) == nil)
        #expect(PerfWorkload.selected(arguments: ["Fichero", "--uitesting"], environment: ["FICHERO_PERF_WORKLOAD": "w1"]) == nil)
        #expect(PerfWorkload.selected(arguments: ["Fichero", "--uitesting"], environment: [:]) == nil)
    }
}
#endif
