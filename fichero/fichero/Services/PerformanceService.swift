import Combine
import Foundation
import Observation
import os.log
import QuartzCore

/// Performance monitoring and benchmarking service
@MainActor
@Observable
class PerformanceService {

    /// Container for benchmark statistics
    struct BenchmarkStatistics {
        let count: Int
        let average: TimeInterval
        let min: TimeInterval
        let max: TimeInterval
    }

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "monitoring")
    private var benchmarks: [String: [TimeInterval]] = [:]
    private var memoryMeasurements: [String: [Int64]] = [:]

    // MARK: - Benchmarking

    /// Start a performance benchmark
    func startBenchmark(_ name: String) -> PerformanceBenchmark {
        logger.info("Starting benchmark: {\(name)}")
        return PerformanceBenchmark(name: name, service: self)
    }

    /// Record a benchmark result
    func recordBenchmark(_ name: String, duration: TimeInterval) {
        if benchmarks[name] == nil {
            benchmarks[name] = []
        }
        benchmarks[name]?.append(duration)

        logger.info("Benchmark {\(name)}: {\(duration)} seconds")
    }

    /// Get average duration for a benchmark
    func averageDuration(for name: String) -> TimeInterval? {
        guard let durations = benchmarks[name], !durations.isEmpty else { return nil }
        return durations.reduce(0, +) / TimeInterval(durations.count)
    }

    /// Get benchmark statistics
    func benchmarkStatistics(for name: String) -> BenchmarkStatistics? {
        guard let durations = benchmarks[name], !durations.isEmpty else { return nil }

        let count = durations.count
        let average = durations.reduce(0, +) / TimeInterval(count)
        let minDuration = durations.min() ?? 0
        let maxDuration = durations.max() ?? 0

        return BenchmarkStatistics(
            count: count,
            average: average,
            min: minDuration,
            max: maxDuration
        )
    }

    // MARK: - Memory Monitoring

    /// Measure current memory usage
    func currentMemoryUsage() -> Int64 {
        var taskInfo = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info>.size) / 4

        let result: kern_return_t = withUnsafeMutablePointer(to: &taskInfo) {
            $0.withMemoryRebound(to: integer_t.self, capacity: 1) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }

        if result == KERN_SUCCESS {
            let usedBytes = Int64(taskInfo.phys_footprint)
            logger.debug("Current memory usage: {\(usedBytes)} bytes")
            return usedBytes
        } else {
            logger.error("Failed to get memory usage: {\(result)}")
            return 0
        }
    }

    /// Record memory measurement
    func recordMemoryMeasurement(_ name: String) {
        let memoryUsage = currentMemoryUsage()

        if memoryMeasurements[name] == nil {
            memoryMeasurements[name] = []
        }
        memoryMeasurements[name]?.append(memoryUsage)

        logger.info("Memory measurement {\(name)}: {\(memoryUsage)} bytes")
    }

    /// Get average memory usage for a measurement
    func averageMemoryUsage(for name: String) -> Int64? {
        guard let measurements = memoryMeasurements[name], !measurements.isEmpty else { return nil }
        return measurements.reduce(0, +) / Int64(measurements.count)
    }

    // MARK: - Frame Rate Monitoring

    /// Frame rate monitoring data
    struct FrameRateData {
        var frameCount: Int = 0
        var totalTime: TimeInterval = 0
        var lastFrameTime: TimeInterval = 0
    }

    private var frameRateData: [String: FrameRateData] = [:]

    /// Start frame rate monitoring
    func startFrameRateMonitoring(_ name: String) {
        frameRateData[name] = FrameRateData()
        logger.info("Started frame rate monitoring: {\(name)}")
    }

    /// Record frame time
    func recordFrameTime(_ name: String) {
        let currentTime = CACurrentMediaTime()

        guard var data = frameRateData[name] else { return }

        if data.lastFrameTime > 0 {
            let frameTime = currentTime - data.lastFrameTime
            data.totalTime += frameTime
            data.frameCount += 1

            // Calculate current FPS
            if data.totalTime > 0 {
                let currentFPS = Double(data.frameCount) / data.totalTime
                logger.debug("Current FPS for {\(name)}: {\(currentFPS)}")
            }
        }

        data.lastFrameTime = currentTime
        frameRateData[name] = data
    }

    /// Get current frame rate
    func currentFrameRate(for name: String) -> Double? {
        guard let data = frameRateData[name], data.totalTime > 0 else { return nil }
        return Double(data.frameCount) / data.totalTime
    }

    /// Stop frame rate monitoring and get results
    func stopFrameRateMonitoring(_ name: String) -> (averageFPS: Double, frameCount: Int)? {
        guard let data = frameRateData[name], data.totalTime > 0 else { return nil }

        let averageFPS = Double(data.frameCount) / data.totalTime
        logger.info("Frame rate results for {\(name)}: {\(averageFPS)} FPS over {\(data.frameCount)} frames")

        frameRateData.removeValue(forKey: name)
        return (averageFPS, data.frameCount)
    }

    // MARK: - Performance Alerts

    /// Check if performance is below threshold
    func checkPerformanceAlert(_ name: String, threshold: TimeInterval) -> Bool {
        guard let stats = benchmarkStatistics(for: name) else { return false }

        if stats.average > threshold {
            logger.warning("Performance alert: {\(name)} average {\(stats.average)} exceeds threshold {\(threshold)}")
            return true
        }

        return false
    }

    /// Check if memory usage is too high
    func checkMemoryAlert(_ name: String, thresholdBytes: Int64) -> Bool {
        guard let avgMemory = averageMemoryUsage(for: name) else { return false }

        if avgMemory > thresholdBytes {
            logger.warning(
                "Memory alert: {\(name)} average memory {\(avgMemory)} bytes exceeds threshold {\(thresholdBytes)}"
            )
            return true
        }

        return false
    }

    // MARK: - Reporting

    /// Generate performance report
    func generatePerformanceReport() -> String {
        var report = "=== Performance Report ===\n\n"

        // Benchmark results
        report += "Benchmark Results:\n"
        for (name, _) in benchmarks {
            if let stats = benchmarkStatistics(for: name) {
                report += "  {\(name)}: {\(stats.count)} runs, "
                report += "avg {\(stats.average)}s, min {\(stats.min)}s, max {\(stats.max)}s\n"
            }
        }

        // Memory results
        report += "\nMemory Usage:\n"
        for (name, _) in memoryMeasurements {
            if let avgMemory = averageMemoryUsage(for: name) {
                let avgMB = Double(avgMemory) / (1024 * 1024)
                report += "  {\(name)}: {\(avgMB)} MB average\n"
            }
        }

        // Frame rate results
        report += "\nFrame Rate Monitoring:\n"
        for (name, data) in frameRateData where data.totalTime > 0 {
            let avgFPS = Double(data.frameCount) / data.totalTime
            report += "  {\(name)}: {\(avgFPS)} FPS\n"
        }

        return report
    }

    /// Clear all performance data
    func clearAllData() {
        benchmarks.removeAll()
        memoryMeasurements.removeAll()
        frameRateData.removeAll()
        logger.info("Cleared all performance data")
    }
}

/// Performance benchmark helper class
class PerformanceBenchmark {
    private let name: String
    private weak var service: PerformanceService?
    private let startTime: TimeInterval

    init(name: String, service: PerformanceService) {
        self.name = name
        self.service = service
        self.startTime = CACurrentMediaTime()
    }

    @MainActor
    func end() {
        let endTime = CACurrentMediaTime()
        let duration = endTime - startTime
        service?.recordBenchmark(name, duration: duration)
    }
}
