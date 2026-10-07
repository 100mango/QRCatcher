"""Source contracts only; actual XCTest compilation/runtime remain CI gates."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
UI = (ROOT / 'QRCatcherVisionUITests/QRCatcherVisionUITests.swift').read_text()
HOSTED = (ROOT / 'QRCatcherVisionTests/QRCatcherVisionTests.swift').read_text()


class VisionAsyncContracts(unittest.TestCase):
    def test_held_capture_yields_without_expanding_deadline(self):
        capture = UI.split('private func capture(', 1)[1].split('private func revealPolicyEnding', 1)[0]
        self.assertIn('async {', capture)
        self.assertIn('ContinuousClock.now.advanced(by: .seconds(100))', capture)
        self.assertIn('try await Task.sleep(nanoseconds: 200_000_000)', capture)
        self.assertNotIn('Thread.sleep', capture)
        self.assertNotIn('try? await', capture)

    def test_every_capture_and_export_call_is_awaited(self):
        calls = [line.strip() for line in UI.splitlines()
                 if re.search(r'\b(?:capture|saveUsingSystemFileExporter)\(', line) and 'func ' not in line]
        self.assertEqual(len(calls), 12)
        for line in calls:
            self.assertRegex(line, r'await (?:capture|saveUsingSystemFileExporter)\(')
        for name in ['testRealPhotosImportCopyAndReopen', 'testRealFilesImportAndReopen', 'testChineseEmptyPhotosResultAndOfflinePolicy', 'testChineseOfflinePolicyEndingAndReturn']:
            self.assertIn('func ' + name + '() async {', UI)

    def test_ack_identity_and_success_remain_mandatory(self):
        self.assertIn('XCTAssertEqual(result?["id"] as? String, id)', UI)
        self.assertIn('XCTAssertEqual(result?["success"] as? Bool, true', UI)
        self.assertIn('else { XCTFail("Held simulator capture acknowledgement:', UI)
        self.assertIn('try JSONSerialization.jsonObject(with: Data(contentsOf: ack))', UI)

    def test_async_teardown_holds_failure_capture_before_termination(self):
        teardown = UI.split('override func tearDown() async throws {', 1)[1].split('private func capture', 1)[0]
        self.assertIn('defer { if let interruptionGuard { removeUIInterruptionMonitor(interruptionGuard) } }', teardown)
        self.assertLess(teardown.index('await capture("vision-failure")'), teardown.index('app.terminate()'))
        self.assertIn('try? FileManager.default.removeItem(at: request); try? FileManager.default.removeItem(at: ack)', UI)

    def test_failure_capture_never_requests_another_ax_snapshot(self):
        teardown = UI.split('override func tearDown() async throws {', 1)[1].split('private func capture', 1)[0]
        self.assertNotIn('debugDescription', teardown)
        self.assertIn('await capture("vision-failure")', teardown)
        capture = UI.split('private func capture(', 1)[1].split('private func revealPolicyEnding', 1)[0]
        self.assertIn('if name != "vision-failure" {\n            let description = String(app.debugDescription.prefix(20000))', capture)
        self.assertIn('VISION_FAILURE_CAPTURE_WITHOUT_NEW_AX_QUERY', capture)
        self.assertIn('VISION_FAILURE_CAPTURE_DIAGNOSTIC', capture)

    def test_async_export_wait_uses_concurrency_safe_waiter(self):
        self.assertIn('let outcome = await XCTWaiter.fulfillment(of: [finished], timeout: 20)', UI)
        self.assertIn('XCTAssertEqual(outcome, .completed, app.debugDescription)', UI)
        self.assertNotIn('XCTWaiter.wait(', UI)

    def test_hosted_observer_waits_for_completion_and_cancels_on_exit(self):
        case = HOSTED.split('func testActualReadPersistsAndReopens()', 1)[1].split('func testCancellationAndSafeActions', 1)[0]
        self.assertLess(case.index('session.read(url: fixture)'), case.index('session.$isReading'))
        self.assertLess(case.index('session.$isReading'), case.index('await XCTWaiter.fulfillment'))
        self.assertIn('.dropFirst().filter { !$0 }.prefix(1)', case)
        self.assertIn('timeout: 60)', case)
        self.assertIn('defer { observation.cancel() }', case)
        self.assertIn('defer { session.cancel() }', case)
        for value in ['XCTAssertEqual(outcome, .completed)', 'XCTAssertFalse(session.isReading)', 'XCTAssertNil(session.error)', 'VISION_ACTUAL_READ_COMPLETION']:
            self.assertIn(value, case)

    def test_hosted_exact_payload_precedes_independent_persistence_assertions(self):
        case = HOSTED.split('func testActualReadPersistsAndReopens()', 1)[1].split('func testCancellationAndSafeActions', 1)[0]
        self.assertLess(case.index('try XCTUnwrap(session.payload'), case.index('XCTAssertEqual(makeHistory'))
        self.assertEqual(case.count(', "QRCatcher 你好 🌈 123")'), 3)
        self.assertNotIn(', session.payload)', case)


if __name__ == '__main__':
    unittest.main()
