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
            cancelled.append(job)
        }
        while await codec.waitingProcessingCount < 30 { await Task.yield() }
        for job in cancelled { job.cancel() }
        // Queued cancellation must finish while the first native operation is
        // still suspended, releasing every obsolete captured image promptly.
        for job in cancelled { do { _ = try await job.value; XCTFail("Cancelled queued job ran") } catch is CancellationError {} catch { XCTFail("Unexpected \(error)") } }
        let queuedAfterCancel = await codec.waitingProcessingCount
        XCTAssertEqual(queuedAfterCancel, 0)
        let last = Task { try await codec.withExclusiveProcessing {
            await probe.enter(); await probe.leave(); return "newest"
        } }
        for _ in 0..<20 { await Task.yield() }
        let during = await probe.maximum
        XCTAssertEqual(during, 1)
        await probe.release()
        do { _ = try await first.value; XCTFail("Cancelled completion must not become a result") } catch is CancellationError {} catch { XCTFail("Unexpected \(error)") }
        let final = try await last.value, maximum = await probe.maximum, starts = await probe.starts
        XCTAssertEqual(final, "newest"); XCTAssertEqual(maximum, 1); XCTAssertEqual(starts, 2)
    }
    func testActualWatchPortableIndependentGoldenPhotos() async throws {
        let codec = WatchPhotoCodec()
        for (name, expected) in ["ascii":["https://example.com/qrcatcher?source=golden"], "unicode":["QRCatcher 你好 🌈 123"], "rotated":["QRCatcher 你好 🌈 123"], "multiple":["https://example.com/qrcatcher?source=golden", "QRCatcher 你好 🌈 123"], "invalid":[], "eci-utf8":["你好 🌈"], "eci-latin1":["Café"], "eci-shiftjis":["日本語"], "eci-mixed":["Café 你好"]] {
            let prepared = try await codec.prepare(fixture(name))
            let values = try await codec.decode(prepared)
            XCTAssertEqual(Set(values), Set(expected), name)
            XCTAssertEqual(values.count, expected.count, name)
        }
    }
    func testDecodeThenDurableDuplicatesDatesAndPNGReopen() async throws {
        let codec = WatchPhotoCodec(), path = try url()
        let png = try await codec.prepare(fixture("unicode"))
        let payloads = try await codec.decode(png)
        XCTAssertEqual(payloads, ["QRCatcher 你好 🌈 123"])
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
    private func reply(for record: WatchRecord, payloads: [String] = ["Phone result"], status: String = "completed") throws -> Data {
        try JSONSerialization.data(withJSONObject: ["kind":"qrcatcher.decode.result", "version":1,
            "recordID":record.id.uuidString, "requestID":try XCTUnwrap(record.phoneRequest).uuidString,
            "sourceSHA256":record.sourceSHA256, "payloads":payloads, "status":status], options: [.sortedKeys])
    }
    func testStageSyntheticReplyForSeparateProcessRelaunchGate() async throws {
        let path = WatchHistory.defaultURL().deletingLastPathComponent().appendingPathComponent("49F5E6A7-20ED-4BD9-BF4E-C4B44F652F21.json")
        // Reset only this fixed synthetic archive/inbox, never production data.
        for file in [path, WatchReplyJournal.location(for: path)] where FileManager.default.fileExists(atPath: file.path) { try FileManager.default.removeItem(at: file) }
        let codec = WatchPhotoCodec(), source = try await codec.prepare(fixture("unicode"))
        let decoded = try await codec.decode(source)
        let history = WatchHistory(url: path)
        var record = try history.append(source: source, payloads: [])
        record.phoneRequest = UUID(); record.phoneState = "pending"; try history.replace(record)
        let journal = WatchReplyJournal(folder: WatchReplyJournal.location(for: path))
        try journal.stage(reply(for: record, payloads: decoded))
        XCTAssertEqual(history.records[0].phoneState, "pending"); XCTAssertTrue(history.records[0].payloads.isEmpty)
        print("WATCH_SYNTHETIC_DURABLE_REPLY_STAGED: production replay must occur in the later app process, not here")
    }
    func testIncomingReplySurvivesInterruptionBeforeMainActorCommitAndDuplicateReplay() throws {
        let path = try url(), history = WatchHistory(url: path)
        var record = try history.append(source: fixture("unicode"), payloads: [])
        record.phoneRequest = UUID(); record.phoneState = "pending"; try history.replace(record)
        let incoming = try reply(for: record), journal = WatchReplyJournal(folder: WatchReplyJournal.location(for: path))
        let staged = try journal.stage(incoming)
        XCTAssertEqual(try Data(contentsOf: staged), incoming)
        XCTAssertTrue(WatchHistory(url: path).records[0].payloads.isEmpty)
        // Process interruption here loses every object above, but not the owned
        // journal. A new history/transport instance replays without connectivity.
        let relaunchedHistory = WatchHistory(url: path)
        let relaunched = WatchPhoneTransport(history: relaunchedHistory)
        XCTAssertEqual(relaunchedHistory.records[0].payloads, ["Phone result"])
        XCTAssertEqual(relaunchedHistory.records[0].phoneState, "completed")
        XCTAssertTrue(try journal.pending().isEmpty)
        let committed = try Data(contentsOf: path)
        try journal.stage(incoming); try relaunched.replayPendingReplies()
        XCTAssertEqual(try Data(contentsOf: path), committed)
        XCTAssertTrue(try journal.pending().isEmpty)
    }
    func testReplyJournalKeepsConflictingOriginalAndRecoversBoundedOrphans() throws {
        let path = try url(), history = WatchHistory(url: path)
        var orphan = WatchRecord(id: UUID(), createdAt: Date(), sourcePNG: try fixture("unicode"), sourceSHA256: String(repeating: "a", count: 64), payloads: [], phoneRequest: UUID(), phoneState: "pending")
        let journal = WatchReplyJournal(folder: WatchReplyJournal.location(for: path))
        let first = try reply(for: orphan), stored = try journal.stage(first)
        XCTAssertEqual(try journal.stage(first), stored)
        XCTAssertThrowsError(try journal.stage(reply(for: orphan, payloads: ["Conflicting result"])))
        XCTAssertEqual(try Data(contentsOf: stored), first)
        for _ in 1..<WatchReplyJournal.countLimit { orphan.phoneRequest = UUID(); try journal.stage(reply(for: orphan)) }
        orphan.phoneRequest = UUID()
        XCTAssertThrowsError(try journal.stage(reply(for: orphan)))
        XCTAssertEqual(try journal.pending().count, WatchReplyJournal.countLimit)
        let transport = WatchPhoneTransport(history: history)
        try transport.replayPendingReplies()
        XCTAssertTrue(history.records.isEmpty); XCTAssertTrue(try journal.pending().isEmpty)
        try journal.stage(reply(for: orphan)); XCTAssertEqual(try journal.pending().count, 1)
    }
    func testUnreadableHistoryRetainsStagedReplyAndOtherStoreInbox() throws {
        let path = try url(), sentinel = Data("Unreadable original".utf8)
        try sentinel.write(to: path)
        let record = WatchRecord(id: UUID(), createdAt: Date(), sourcePNG: try fixture("unicode"), sourceSHA256: String(repeating: "b", count: 64), payloads: [], phoneRequest: UUID(), phoneState: "pending")
        let journal = WatchReplyJournal(folder: WatchReplyJournal.location(for: path)), bytes = try reply(for: record)
        let stored = try journal.stage(bytes)
        let broken = WatchPhoneTransport(history: WatchHistory(url: path))
        XCTAssertThrowsError(try broken.replayPendingReplies())
        XCTAssertEqual(try Data(contentsOf: path), sentinel); XCTAssertEqual(try Data(contentsOf: stored), bytes)
        let other = WatchHistory(url: path.deletingLastPathComponent().appendingPathComponent("other.json"))
        _ = WatchPhoneTransport(history: other)
        XCTAssertEqual(try Data(contentsOf: stored), bytes, "An isolated archive must not consume another archive's journal")
    }
    func testFailedOrMalformedPhoneReplyKeepsPreviousDecodedResult() throws {
        let history = WatchHistory(url: try url())
        var record = try history.append(source: fixture("unicode"), payloads: ["Existing result"])
        record.phoneRequest = UUID(); record.phoneState = "pending"; try history.replace(record)
        let transport = WatchPhoneTransport(history: history)
        var response: [String: Any] = ["kind":"qrcatcher.decode.result", "version":1, "recordID":record.id.uuidString,
            "requestID":try XCTUnwrap(record.phoneRequest).uuidString, "sourceSHA256":record.sourceSHA256,
            "payloads":[], "status":"completed"]
        let before = try Data(contentsOf: history.url)
        try transport.accept(JSONSerialization.data(withJSONObject: response))
        XCTAssertEqual(try Data(contentsOf: history.url), before, "Invalid completed/empty state must be ignored")
        response["status"] = "no_qr"
        try transport.accept(JSONSerialization.data(withJSONObject: response))
        let reopened = WatchHistory(url: history.url)
        XCTAssertEqual(reopened.records[0].payloads, ["Existing result"])
        XCTAssertEqual(reopened.records[0].sourcePNG, record.sourcePNG)
        XCTAssertEqual(reopened.records[0].phoneState, "failed")
        XCTAssertNotNil(reopened.records[0].phoneError)
    }
    func testReceivedPhoneReplyRejectsOversizeAndSymbolicFiles() throws {
        let folder = try url().deletingLastPathComponent(), regular = folder.appendingPathComponent("reply.json")
        let data = Data("{\"status\":\"synthetic\"}".utf8); try data.write(to: regular)
        XCTAssertEqual(try WatchPhoneTransport.readBoundedReply(regular), data)
        let link = folder.appendingPathComponent("linked.json")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: regular)
        XCTAssertThrowsError(try WatchPhoneTransport.readBoundedReply(link))
        let handle = try FileHandle(forWritingTo: regular); try handle.truncate(atOffset: 2 * 1024 * 1024 + 1); try handle.close()
        XCTAssertThrowsError(try WatchPhoneTransport.readBoundedReply(regular))
    }
    func testPhoneResultContractPersistsAndRejectsCancelledOrForeignReplies() throws {
        let history = WatchHistory(url: try url())
        var record = try history.append(source: fixture("unicode"), payloads: [])
        record.phoneRequest = UUID(); record.phoneState = "pending"; try history.replace(record)
        let transport = WatchPhoneTransport(history: history)
        func response(_ request: UUID, _ hash: String) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["kind":"qrcatcher.decode.result","version":1,"recordID":record.id.uuidString,"requestID":request.uuidString,"sourceSHA256":hash,"payloads":["QRCatcher 你好 🌈 123"],"status":"completed"])
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
