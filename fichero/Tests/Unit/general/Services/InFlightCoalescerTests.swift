//
//  InFlightCoalescerTests.swift
//  FicheroTests
//
//  #4572: every thumbnail was fetched exactly twice — concurrent same-key
//  loads raced past the result cache. The coalescer shares the in-flight
//  task; these tests pin that one key = one operation, errors don't poison
//  retries, and distinct keys stay independent.
//

import Foundation
import Testing
@testable import Fichero

@MainActor
struct InFlightCoalescerTests {

    @Test("Concurrent same-key loads run the operation once")
    func concurrentLoadsCoalesce() async throws {
        let coalescer = InFlightCoalescer<String>()
        let gate = AsyncStream<Void>.makeStream()
        var runs = 0

        async let first: String = coalescer.run("doc-1") {
            runs += 1
            for await _ in gate.stream { break }  // hold until released
            return "image"
        }
        // Give the first call time to register its task.
        await Task.yield()
        async let second: String = coalescer.run("doc-1") {
            runs += 1
            return "image-second"
        }
        await Task.yield()
        gate.continuation.yield()
        gate.continuation.finish()

        let (firstValue, secondValue) = try await (first, second)
        #expect(firstValue == "image" && secondValue == "image", "both callers share the first task's value")
        #expect(runs == 1, "the second load must be absorbed, not executed")
        #expect(coalescer.coalescedCount == 1)
    }

    @Test("A failed load clears the slot so a retry can succeed")
    func failureDoesNotPoisonRetries() async throws {
        struct Boom: Error {}
        let coalescer = InFlightCoalescer<String>()

        await #expect(throws: Boom.self) {
            try await coalescer.run("doc-1") { throw Boom() }
        }
        let retried = try await coalescer.run("doc-1") { "recovered" }
        #expect(retried == "recovered")
    }

    @Test("Distinct keys run independently")
    func distinctKeysDoNotShare() async throws {
        let coalescer = InFlightCoalescer<Int>()
        async let keyA: Int = coalescer.run("a") { 1 }
        async let keyB: Int = coalescer.run("b") { 2 }
        let (valueA, valueB) = try await (keyA, keyB)
        #expect(valueA == 1 && valueB == 2)
        #expect(coalescer.coalescedCount == 0)
    }
}
