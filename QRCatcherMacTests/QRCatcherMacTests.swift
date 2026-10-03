import XCTest
import CoreData
import AppKit
import UniformTypeIdentifiers
import SwiftUI
@testable import QRCatcherMac

@MainActor
final class QRCatcherMacTests: QRManagedStoreTestCase {
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        cleanupLater(url)
        return url
    }

    func testActualNativeSplitPaneLabelsPreserveAccessibleChildren() async throws {
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        let host = NSHostingView(rootView: MacMainView(workspace: workspace, history: history).frame(minWidth: 760, minHeight: 520))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 640),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        func descendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap(descendants) }
        for _ in 0..<20 {
            host.layoutSubtreeIfNeeded()
            if descendants(host).filter({ $0.accessibilityIdentifier().hasPrefix("mac.pane.") }).count == 2 { break }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        for (identifier, label) in [("mac.pane.history", "Saved QR history"), ("mac.pane.result", "QR Result")] {
            let pane = try XCTUnwrap(descendants(host).first { $0.accessibilityIdentifier() == identifier })
            var ancestor = pane.superview
            while let current = ancestor, !(current is NSSplitView) { ancestor = current.superview }
            XCTAssertTrue(ancestor is NSSplitView)
            XCTAssertTrue(pane.isAccessibilityElement())
            XCTAssertEqual(pane.accessibilityRole(), .group)
            XCTAssertEqual(pane.accessibilityLabel(), QRL(label))
            XCTAssertFalse((pane.accessibilityChildren() ?? []).isEmpty, "Semantic labels must preserve pane children")
        }
    }

    func testFilesFailureAndCancellationRetainSelectedPayloadAndHistory() async throws {
        let folder = try directory(), history = makeHistory(url: folder.appendingPathComponent("history.sqlite"))
        let workspace = MacWorkspace(history: history); workspace.accept(["keep this selection"])
        let url = folder.appendingPathComponent("oversized.png")
        FileManager.default.createFile(atPath: url.path, contents: Data())
        let handle = try FileHandle(forWritingTo: url); try handle.truncate(atOffset: UInt64(QRBoundedPhotoFile.maximumBytes + 1)); try handle.close()
        workspace.read(url: url)
        for _ in 0..<100 where workspace.isReading { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertFalse(workspace.isReading); XCTAssertNotNil(workspace.error)
        XCTAssertEqual(workspace.payload, "keep this selection"); XCTAssertEqual(history.items.map(\.payload), ["keep this selection"])
        workspace.read(url: url); workspace.cancelRead()
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(workspace.payload, "keep this selection"); XCTAssertEqual(history.items.count, 1)
    }

    func testSafePayloadPolicy() {
        XCTAssertEqual(QRPayload.safeWebURL("example.com")?.absoluteString, "https://example.com")
        XCTAssertNotNil(QRPayload.safeWebURL("HTTPS://example.com/a?q=1"))
        for text in ["", "plain text", "javascript:alert(1)", "file:///etc/passwd", "tel:123", "https://user:secret@example.com", "http://"] {
            XCTAssertNil(QRPayload.safeWebURL(text), text)
        }
    }

    func testIndependentGoldenImages() throws {
        let expected = ["ascii": ["https://example.com/qrcatcher?source=golden"], "unicode": ["QRCatcher 你好 🌈 123"],
                        "rotated": ["QRCatcher 你好 🌈 123"], "invalid": [],
                        "multiple": ["https://example.com/qrcatcher?source=golden", "QRCatcher 你好 🌈 123"]]
        for (name, payloads) in expected {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png"))
            XCTAssertEqual(Set(try QRImageCodec.decode(data: Data(contentsOf: url))), Set(payloads), name)
        }
    }

    func testExportedPNGRescansAndHasQuietZone() throws {
        for value in ["https://example.com/", "QRCatcher 你好 🌈 123", "javascript:alert(1)"] {
            let data = try XCTUnwrap(QRImageCodec.png(payload: value))
            XCTAssertEqual(try QRImageCodec.decode(data: data), [value])
            let image = try XCTUnwrap(NSBitmapImageRep(data: data))
            for point in [(0,0), (31,31), (image.pixelsWide-1,image.pixelsHigh-1)] {
                let color = try XCTUnwrap(image.colorAt(x: point.0, y: point.1)?.usingColorSpace(.deviceRGB))
                XCTAssertEqual(color.redComponent, 1, accuracy: 0.001)
                XCTAssertEqual(color.greenComponent, 1, accuracy: 0.001)
            }
        }
        XCTAssertNil(QRImageCodec.png(payload: ""))
        XCTAssertThrowsError(try QRImageCodec.decode(data: Data("not an image".utf8)))
        XCTAssertThrowsError(try QRImageCodec.decode(data: Data(count: 50 * 1024 * 1024 + 1)))
    }

    func testEncodedClipboardPathRejectsOversizedSourceBeforeRasterExpansion() async throws {
        let pasteboard = NSPasteboard.withUniqueName()
        defer { pasteboard.clearContents(); pasteboard.releaseGlobally() }
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        workspace.accept(["Keep this result"])
        for name in ["oversized-edge", "oversized-area"] {
            let data = try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "png")))
            XCTAssertLessThan(data.count, 100 * 1024, "This fixture is small encoded data with excessive source dimensions")
            XCTAssertThrowsError(try QRImageCodec.decode(data: data)) { error in
                XCTAssertEqual((error as NSError).domain, "QRCatcher.Image")
                XCTAssertEqual((error as NSError).code, 3, "Metadata must reject the dimensions before thumbnail creation")
            }
            pasteboard.clearContents(); XCTAssertTrue(pasteboard.setData(data, forType: .png))
            workspace.error = nil
            workspace.pasteImage(from: pasteboard)
            XCTAssertTrue(workspace.isReading, "The explicit paste must enqueue encoded bytes, not expand NSImage on the main actor")
            for _ in 0..<50 { if !workspace.isReading { break }; try await Task.sleep(nanoseconds: 100_000_000) }
            XCTAssertNotNil(workspace.error)
            XCTAssertEqual(workspace.payload, "Keep this result")
            XCTAssertEqual(history.items.count, 1)
        }
        let valid = try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "unicode", withExtension: "png")))
        pasteboard.clearContents(); XCTAssertTrue(pasteboard.setData(valid, forType: .png))
        workspace.pasteImage(from: pasteboard)
        for _ in 0..<50 { if !workspace.isReading { break }; try await Task.sleep(nanoseconds: 100_000_000) }
        XCTAssertEqual(workspace.payload, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(history.items.count, 2)
    }

    func testLegacyModelAndHistoryPreserveNullDateDuplicatesAndReopen() throws {
        let url = try directory().appendingPathComponent("coredata.sqlite")
        let model = QRHistoryStore.model()
        XCTAssertEqual(Set(model.entitiesByName.keys), ["URLEntity"])
        XCTAssertEqual(Set(try XCTUnwrap(model.entitiesByName["URLEntity"]).attributesByName.keys), ["url", "createDate"])
        let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
        let persistent = try coordinator.addPersistentStore(ofType: NSSQLiteStoreType, configurationName: nil, at: url, options: nil)
        let context = NSManagedObjectContext(concurrencyType: .mainQueueConcurrencyType)
        context.persistentStoreCoordinator = coordinator
        for (text, date) in [("legacy duplicate", Date(timeIntervalSince1970: 1431993600)), ("legacy duplicate", Date(timeIntervalSince1970: 1431993500)), ("oldest", Date(timeIntervalSince1970: 0))] {
            let record = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context) as! URLEntity
            record.url = text; record.createDate = date
        }
        _ = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context)
        try context.save(); context.reset(); try coordinator.remove(persistent)
        var history: MacHistory? = makeHistory(url: url)
        XCTAssertNil(history?.error)
        XCTAssertEqual(history?.items.count, 4)
        XCTAssertEqual(history?.items.filter { $0.payload == "legacy duplicate" }.count, 2)
        XCTAssertTrue(try XCTUnwrap(history).record("legacy duplicate"))
        XCTAssertEqual(history?.items.count, 4)
        XCTAssertTrue(try XCTUnwrap(history).record("new value"))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: try XCTUnwrap(history).exportData()) as? [String: Any])
        let rows = try XCTUnwrap(json["records"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 5)
        XCTAssertEqual(rows.filter { ($0["payload"] as? String) == "legacy duplicate" }.count, 2)
        XCTAssertEqual(rows.filter { $0["payload"] is NSNull }.count, 1)
        XCTAssertEqual(rows.compactMap { $0["createdAtUnixSeconds"] as? Double }.suffix(3), [1431993600,1431993500,0])
        try history?.close(); history = nil
        let reopened = makeHistory(url: url)
        XCTAssertEqual(reopened.items.count, 5)
        let new = try XCTUnwrap(reopened.items.first(where: { $0.payload == "new value" }))
        reopened.delete(new)
        XCTAssertEqual(makeHistory(url: url).items.count, 4)
    }

    func testUnreadableStoreRemainsIntactAndCopyStillWorks() throws {
        let url = try directory().appendingPathComponent("coredata.sqlite")
        let data = Data("not a sqlite database - preserve me".utf8)
        try data.write(to: url)
        let history = makeHistory(url: url)
        XCTAssertNotNil(history.error)
        XCTAssertThrowsError(try history.exportData())
        let workspace = MacWorkspace(history: history)
        workspace.accept(["Safe copy after storage error"])
        XCTAssertEqual(workspace.payload, "Safe copy after storage error")
        let original = NSPasteboard.general.string(forType: .string)
        defer { NSPasteboard.general.clearContents(); if let original { NSPasteboard.general.setString(original, forType: .string) } }
        workspace.copy()
        XCTAssertEqual(NSPasteboard.general.string(forType: .string), workspace.payload)
        XCTAssertEqual(try Data(contentsOf: url), data)
        XCTAssertNotNil(history.error)
    }

    func testCancelledDecodeCannotReplaceSelection() async throws {
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        let data = try XCTUnwrap(QRImageCodec.png(payload: "stale"))
        workspace.read(data: data)
        workspace.cancelRead()
        workspace.accept(["current"])
        try await Task.sleep(nanoseconds: 500_000_000)
        XCTAssertEqual(workspace.payload, "current")
        XCTAssertEqual(history.items.map(\.payload), ["current"])
        XCTAssertFalse(workspace.isReading)
    }

    func testLatePhotoProviderCannotReplaceASelectedResult() async throws {
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        let data = try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "unicode", withExtension: "png")))
        let stale = workspace.beginExternalLoad()
        workspace.accept(["Keep my latest selection"])
        workspace.completeExternalLoad(stale, data: data, error: nil)
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertEqual(workspace.payload, "Keep my latest selection")
        XCTAssertEqual(history.items.count, 1)
        let current = workspace.beginExternalLoad()
        workspace.completeExternalLoad(current, data: data, error: nil)
        for _ in 0..<50 { if !workspace.isReading { break }; try await Task.sleep(nanoseconds: 100_000_000) }
        XCTAssertEqual(workspace.payload, "QRCatcher 你好 🌈 123")
        XCTAssertEqual(history.items.count, 2)
    }

    func testImageDropUsesRealPixelsAndRejectsLateDelivery() async throws {
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history)
        let data = try Data(contentsOf: XCTUnwrap(Bundle(for: Self.self).url(forResource: "ascii", withExtension: "png")))
        let provider = NSItemProvider()
        provider.registerDataRepresentation(forTypeIdentifier: UTType.image.identifier, visibility: .all) { completion in
            completion(data, nil)
            return nil
        }
        XCTAssertTrue(workspace.dropped([provider]))
        for _ in 0..<50 {
            if workspace.payload != nil { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertEqual(workspace.payload, "https://example.com/qrcatcher?source=golden")
        XCTAssertEqual(history.items.count, 1)
        let delayed = NSItemProvider()
        delayed.registerDataRepresentation(forTypeIdentifier: UTType.image.identifier, visibility: .all) { completion in
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.3) { completion(data, nil) }
            return nil
        }
        XCTAssertTrue(workspace.dropped([delayed]))
        workspace.accept(["Newer explicit selection"])
        try await Task.sleep(nanoseconds: 700_000_000)
        XCTAssertEqual(workspace.payload, "Newer explicit selection")
    }

    func testRepeatedImportsCancelQueuedWorkAndBoundHeavyConcurrency() async throws {
        let entered = expectation(description: "First heavy operation started")
        let probe = DecodeConcurrencyProbe(started: entered)
        let decoder = QRDecodeWorker(operation: { data in try probe.process(data) })
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        let workspace = MacWorkspace(history: history, decoder: decoder)
        workspace.read(data: Data("first".utf8))
        await fulfillment(of: [entered], timeout: 5)
        for index in 0..<30 { workspace.read(data: Data("discarded-\(index)".utf8)) }
        workspace.read(data: Data("latest".utf8))
        probe.release.signal()
        for _ in 0..<50 {
            if workspace.payload == "latest" { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertEqual(workspace.payload, "latest")
        XCTAssertEqual(history.items.map(\.payload), ["latest"])
        XCTAssertEqual(probe.snapshot.started, ["first", "latest"])
        XCTAssertEqual(probe.snapshot.maximumConcurrent, 1)
    }

    func testRapidHistorySelectionLastIntentClearAndNewImport() async throws {
        let history = makeHistory(url: try directory().appendingPathComponent("coredata.sqlite"))
        for value in ["A","B","C"] { XCTAssertTrue(history.record(value)) }
        let session = MacWorkspace(history: history)
        let ids = Dictionary(uniqueKeysWithValues: history.items.map { ($0.text, $0.id) })
        session.queueSelection(ids["A"]); session.queueSelection(ids["B"]); session.queueSelection(ids["C"])
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(session.payload, "C"); XCTAssertEqual(history.items.count, 3)
        session.queueSelection(ids["A"]); session.queueSelection(nil)
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertNil(session.selection); XCTAssertEqual(session.payload, "C")
        session.queueSelection(ids["A"]); session.accept(["new imported result"])
        try await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(session.payload, "new imported result"); XCTAssertEqual(history.items.count, 4)
    }
    func testCameraAbsenceIsExplicit() throws {
        let camera = MacCamera()
        print("Actual camera inventory:", camera.devices.map(\.localizedName))
        if camera.devices.isEmpty {
            camera.start(deviceID: nil)
            XCTAssertTrue(camera.status.contains("No camera"))
            XCTAssertFalse(camera.running)
        } else {
            throw XCTSkip("Physical camera absence cannot be asserted on this runner")
        }
    }
}

/// A synchronous controllable engine, injected only by this test bundle.
private final class DecodeConcurrencyProbe: @unchecked Sendable {
    let release = DispatchSemaphore(value: 0)
    private let started: XCTestExpectation
    private let lock = NSLock()
    private var active = 0
    private var maximumConcurrent = 0
    private var values: [String] = []
    init(started: XCTestExpectation) { self.started = started }
    var snapshot: (started: [String], maximumConcurrent: Int) {
        lock.lock(); defer { lock.unlock() }; return (values, maximumConcurrent)
    }
    func process(_ data: Data) throws -> [String] {
        let value = String(decoding: data, as: UTF8.self)
        lock.lock(); active += 1; maximumConcurrent = max(maximumConcurrent, active); values.append(value); lock.unlock()
        defer { lock.lock(); active -= 1; lock.unlock() }
        if value == "first" {
            started.fulfill()
            guard release.wait(timeout: .now() + 5) == .success else { throw CocoaError(.userCancelled) }
        }
        return [value]
    }
}

@MainActor
final class QRCatcherHistoryLocationTests: QRManagedStoreTestCase {
    private func fixture() throws -> (root: URL, docs: URL, modern: URL, locations: QRHistoryLocations) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("Library/Containers/100mango.QRCatcher/Data")
        let docs = root.appendingPathComponent("Documents", isDirectory: true)
        let folder = root.appendingPathComponent("Library/Application Support/100mango.QRCatcher", isDirectory: true)
        try FileManager.default.createDirectory(at: docs, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        cleanupLater(root.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent())
        let modern = folder.appendingPathComponent("coredata.sqlite")
        let owned = try XCTUnwrap(QRHistoryLocations.validatedDocuments(home: root, documents: docs, sandboxed: true))
        return (root, docs, modern, QRHistoryLocations(nativeURL: modern, previousURL: owned.appendingPathComponent("coredata.sqlite"), selectionURL: folder.appendingPathComponent("history-location.json")))
    }
    private func files(_ url: URL) -> [String: Data] {
        Dictionary(uniqueKeysWithValues: ["", "-wal", "-shm"].compactMap { suffix in
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: url.path + suffix)) else { return nil }
            return (suffix, data)
        })
    }
    func testOfflinePolicyUsesApprovedMinimalBilingualCopy() {
        XCTAssertTrue(QRPrivacyText.english.hasSuffix("Local data can be deleted through the relevant app or system, and permissions can be revoked in system settings."))
        XCTAssertTrue(QRPrivacyText.simplifiedChinese.hasSuffix("本地数据可通过相应应用或系统删除，权限可在系统设置中撤回。"))
        XCTAssertTrue(QRPrivacyText.english.contains("system services such as iCloud sync"))
        XCTAssertTrue(QRPrivacyText.simplifiedChinese.contains("系统 iCloud 同步"))
        for text in [QRPrivacyText.english, QRPrivacyText.simplifiedChinese] { XCTAssertTrue(text.contains("100mango@gmail.com")) }
    }
    func testSameOwnedContainerSelectsOriginalStoreWithSidecarsAndValuesIntact() throws {
        let f = try fixture(); let legacy = try XCTUnwrap(f.locations.previousURL)
        let old = makeLegacyStore(url: legacy)
        let context = try XCTUnwrap(old.context)
        for (text, seconds) in [("duplicate", 1431993600.0), ("duplicate",1431993500.0), ("text 你好",0.0)] {
            let row = NSEntityDescription.insertNewObject(forEntityName: "URLEntity", into: context) as! URLEntity
            row.url = text; row.createDate = Date(timeIntervalSince1970: seconds)
        }
        try old.save()
        let before = files(legacy)
        XCTAssertNotNil(before["-wal"]); XCTAssertNotNil(before["-shm"])
        XCTAssertEqual(try f.locations.resolve(), legacy)
        XCTAssertEqual(files(legacy), before, "Location selection must not copy, rename, checkpoint or delete store files")
        XCTAssertFalse(FileManager.default.fileExists(atPath: f.modern.path))
        let opened = makeHistory(url: try f.locations.resolve())
        XCTAssertNil(opened.error)
        XCTAssertEqual(opened.items.map(\.payload), ["duplicate", "duplicate", "text 你好"])
        XCTAssertEqual(opened.items.compactMap { $0.createdAt?.timeIntervalSince1970 }, [1431993600,1431993500,0])
        XCTAssertTrue(opened.record("new native scan"))
        XCTAssertEqual(makeHistory(url: legacy).items.count, 4)
        XCTAssertFalse(FileManager.default.fileExists(atPath: f.modern.path))
    }
    func testBothStoresRequireExplicitChoiceAndNeverOverwriteEither() throws {
        let f = try fixture(); let previous = try XCTUnwrap(f.locations.previousURL)
        let old = makeLegacyStore(url: previous); try old.record(payload: "previous payload")
        let new = makeLegacyStore(url: f.modern); try new.record(payload: "native payload")
        let a = files(previous), b = files(f.modern)
        XCTAssertThrowsError(try f.locations.resolve()) { error in
            guard let locationError = error as? QRHistoryLocationError else { return XCTFail("Expected a location error") }
            if case .conflict = locationError {} else { XCTFail("Expected an explicit location conflict") }
        }
        XCTAssertEqual(files(previous), a); XCTAssertEqual(files(f.modern), b)
        let choice = try XCTUnwrap(f.locations.choices.first(where: { $0.id == .previousApp }))
        try f.locations.remember(choice)
        XCTAssertEqual(try f.locations.resolve(), previous)
        XCTAssertEqual(files(previous), a); XCTAssertEqual(files(f.modern), b)
        XCTAssertTrue(FileManager.default.fileExists(atPath: f.modern.path))
    }
    func testMissingExplicitSelectionNeverCreatesAnEmptyReplacement() throws {
        let f = try fixture(); let previous = try XCTUnwrap(f.locations.previousURL)
        try Data("previous store bytes".utf8).write(to: previous)
        try Data("native store bytes".utf8).write(to: f.modern)
        let choice = try XCTUnwrap(f.locations.choices.first(where: { $0.id == .previousApp }))
        try f.locations.remember(choice)
        // Synthetic test-only removal emulates an unavailable selected file.
        try FileManager.default.removeItem(at: previous)
        XCTAssertThrowsError(try f.locations.resolve()) { error in
            guard let locationError = error as? QRHistoryLocationError else { return XCTFail("Expected a location error") }
            if case .selectedStoreMissing = locationError {} else { XCTFail("Must not silently switch histories") }
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: previous.path))
        XCTAssertEqual(try Data(contentsOf: f.modern), Data("native store bytes".utf8))
    }
    func testUnreadableLegacyStoreIsSelectedButNeverReplaced() throws {
        let f = try fixture(); let previous = try XCTUnwrap(f.locations.previousURL)
        let original = Data("unreadable original store".utf8); try original.write(to: previous)
        XCTAssertEqual(try f.locations.resolve(), previous)
        let history = makeHistory(url: previous)
        XCTAssertNotNil(history.error); XCTAssertFalse(history.record("cannot save"))
        XCTAssertEqual(try Data(contentsOf: previous), original)
        XCTAssertFalse(FileManager.default.fileExists(atPath: f.modern.path))
    }
    func testUnsandboxedGeneralDocumentsAndEscapingLinksAreNotRead() throws {
        let f = try fixture()
        XCTAssertNil(QRHistoryLocations.validatedDocuments(home: f.root, documents: f.docs, sandboxed: false))
        let unrelated = f.root.deletingLastPathComponent().appendingPathComponent("unrelated.sqlite")
        try Data("do not read".utf8).write(to: unrelated)
        let previous = try XCTUnwrap(f.locations.previousURL)
        try FileManager.default.createSymbolicLink(at: previous, withDestinationURL: unrelated)
        XCTAssertThrowsError(try f.locations.resolve())
        XCTAssertEqual(try Data(contentsOf: unrelated), Data("do not read".utf8))
        XCTAssertFalse(FileManager.default.fileExists(atPath: f.modern.path))
    }
}
