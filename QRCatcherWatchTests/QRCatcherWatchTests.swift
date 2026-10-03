import XCTest
@testable import QRCatcherWatch

@MainActor final class QRCatcherWatchTests: XCTestCase {
    private var folders: [URL] = []
    override func tearDownWithError() throws { for folder in folders { try? FileManager.default.removeItem(at: folder) }; folders = [] }
    private func url() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true); folders.append(folder)
        return folder.appendingPathComponent("history.json")
    }
    private func fixture(_ name: String) throws -> Data { try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))) }
    func testCancelledReselectionsNeverOverlapSuspendedNativeWork() async throws {
        let codec = WatchPhotoCodec(), probe = WatchAdmissionProbe()
        let first = Task { try await codec.withExclusiveProcessing {
            await probe.enter()
            await probe.waitForRelease() // Deliberately ignores cancellation like a native request may.
            await probe.leave()
            try Task.checkCancellation()
            return "stale"
        } }
        while !(await probe.started) { await Task.yield() }
        first.cancel()
        var cancelled: [Task<String, Error>] = []
        for _ in 0..<30 {
            let job = Task { try await codec.withExclusiveProcessing {
                await probe.enter(); await probe.leave(); return "obsolete"
            } }
            job.cancel(); cancelled.append(job)
        }
        let last = Task { try await codec.withExclusiveProcessing {
            await probe.enter(); await probe.leave(); return "newest"
        } }
        for _ in 0..<20 { await Task.yield() }
        let during = await probe.maximum
        XCTAssertEqual(during, 1)
        await probe.release()
        do { _ = try await first.value; XCTFail("Cancelled completion must not become a result") } catch is CancellationError {} catch { XCTFail("Unexpected \(error)") }
        for job in cancelled { do { _ = try await job.value; XCTFail("Cancelled queued job ran") } catch is CancellationError {} catch { XCTFail("Unexpected \(error)") } }
        let final = try await last.value, maximum = await probe.maximum, starts = await probe.starts
        XCTAssertEqual(final, "newest"); XCTAssertEqual(maximum, 1); XCTAssertEqual(starts, 2)
    }
    func testActualWatchVisionIndependentGoldenPhotos() async throws {
        guard #available(watchOS 27.0, *) else { throw XCTSkip("Local Vision API requires watchOS 27; paired iPhone remains the older-OS path") }
        let codec = WatchPhotoCodec()
        for (name, expected) in ["ascii":["https://example.com/qrcatcher?source=golden"], "unicode":["QRCatcher 你好 🌈 123"], "rotated":["QRCatcher 你好 🌈 123"], "invalid":[]] {
            let prepared = try await codec.prepare(fixture(name))
            let values = try await codec.decode(prepared)
            XCTAssertEqual(values, expected, name)
        }
    }
    func testDecodeThenDurableDuplicatesDatesAndPNGReopen() async throws {
        guard #available(watchOS 27.0, *) else { throw XCTSkip("Watch 27 local decoder") }
        let codec = WatchPhotoCodec(), path = try url()
        let png = try await codec.prepare(fixture("unicode"))
        let payloads = try await codec.decode(png)
        let history = WatchHistory(url: path)
        try history.append(source: png, payloads: payloads, date: Date(timeIntervalSince1970: 100))
        try history.append(source: png, payloads: payloads, date: Date(timeIntervalSince1970: 200))
        let reopened = WatchHistory(url: path)
        XCTAssertNil(reopened.error); XCTAssertEqual(reopened.records.map { $0.createdAt.timeIntervalSince1970 }, [200,100])
        XCTAssertEqual(reopened.records.map(\.payloads), [payloads,payloads])
        XCTAssertEqual(reopened.records.map(\.sourcePNG), [png,png]); XCTAssertNotNil(WatchPhotoCodec.preview(png))
        let values = try await codec.decode(reopened.records[0].sourcePNG); XCTAssertEqual(values, payloads)
        try reopened.remove(reopened.records[0].id)
        XCTAssertEqual(WatchHistory(url: path).records.count, 1)
    }
    func testPrepareClearlyLabeledOfflineUIFixtureThroughRealLocalDecoder() async throws {
        guard #available(watchOS 27.0, *) else { throw XCTSkip("Watch 27 local decoder") }
        let directory = WatchHistory.defaultURL().deletingLastPathComponent()
        let path = directory.appendingPathComponent("81F3B791-5049-4ED7-B88E-9684DA76DDB8.json")
        // Only this explicitly synthetic unit-test archive is reset, never the
        // production collection. The UI test reports this as fixture-fed state.
        if FileManager.default.fileExists(atPath: path.path) { try FileManager.default.removeItem(at: path) }
        let codec = WatchPhotoCodec(), png = try await codec.prepare(fixture("unicode"))
        let values = try await codec.decode(png)
        let history = WatchHistory(url: path); try history.append(source: png, payloads: values)
        XCTAssertEqual(WatchHistory(url: path).records.first?.payloads, ["QRCatcher 你好 🌈 123"])
    }
    func testUnreadableArchiveAndQuotaDoNotReplaceOriginal() throws {
        let path = try url(), sentinel = Data("Unreadable originals must survive".utf8)
        try sentinel.write(to: path)
        let broken = WatchHistory(url: path); XCTAssertNotNil(broken.error)
        XCTAssertThrowsError(try broken.append(source: fixture("ascii"), payloads: ["test"]))
        XCTAssertEqual(try Data(contentsOf: path), sentinel)
        let full = WatchHistory(url: try url()), image = try fixture("ascii")
        for _ in 0..<WatchHistory.maximumRecords { try full.append(source: image, payloads: ["duplicate"]) }
        let original = try Data(contentsOf: full.url)
        XCTAssertThrowsError(try full.append(source: image, payloads: ["overflow"]))
        XCTAssertEqual(try Data(contentsOf: full.url), original); XCTAssertEqual(full.records.count, 50)
    }
    func testOversizedMetadataRejectedBeforeDecode() async throws {
        let codec = WatchPhotoCodec()
        for name in ["oversized-edge", "oversized-area"] {
            XCTAssertFalse(WatchPhotoCodec.validPreparedPNG(try fixture(name)))
            XCTAssertNil(WatchPhotoCodec.preview(try fixture(name)))
            do { _ = try await codec.prepare(fixture(name)); XCTFail("Image metadata limit must reject \(name)") }
            catch { XCTAssertNotNil(error as? WatchStoreError) }
        }
    }
    func testPhoneResultContractPersistsAndRejectsCancelledOrForeignReplies() throws {
        let history = WatchHistory(url: try url())
        var record = try history.append(source: fixture("unicode"), payloads: [])
        record.phoneRequest = UUID(); record.phoneState = "pending"; try history.replace(record)
        let transport = WatchPhoneTransport(history: history)
        func response(_ request: UUID, _ hash: String) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["kind":"qrcatcher.decode.result","version":1,"recordID":record.id.uuidString,"requestID":request.uuidString,"sourceSHA256":hash,"payloads":["QRCatcher 你好 🌈 123"]])
        }
        try transport.accept(response(UUID(), record.sourceSHA256)); XCTAssertTrue(history.records[0].payloads.isEmpty)
        try transport.accept(response(try XCTUnwrap(record.phoneRequest), "foreign")); XCTAssertTrue(history.records[0].payloads.isEmpty)
        try transport.accept(response(try XCTUnwrap(record.phoneRequest), record.sourceSHA256))
        XCTAssertEqual(WatchHistory(url: history.url).records[0].payloads, ["QRCatcher 你好 🌈 123"])
        XCTAssertEqual(history.records[0].phoneState, "completed")
        // This is a schema/state test, not a claim of simulator WC file delivery.
        record.phoneState = "cancelled"; record.payloads = []; try history.replace(record)
        try transport.accept(response(try XCTUnwrap(record.phoneRequest), record.sourceSHA256)); XCTAssertTrue(history.records[0].payloads.isEmpty)
    }
}

private actor WatchAdmissionProbe {
    var started = false
    var maximum = 0
    var starts = 0
    private var active = 0
    private var continuation: CheckedContinuation<Void, Never>?
    func enter() { active += 1; starts += 1; maximum = max(maximum, active) }
    func leave() { active -= 1 }
    func waitForRelease() async { await withCheckedContinuation { continuation = $0; started = true } }
    func release() { continuation?.resume(); continuation = nil }
}
