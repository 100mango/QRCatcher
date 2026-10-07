"""Portable file/retention checks with explicit sips doubles; no native proof."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import vision_store_image as image


def jpeg(count, content=b'x'):
    return b'\xff\xd8' + content * (count - 4) + b'\xff\xd9'


class StoreImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.original = self.root / image.ORIGINAL_NAME
        self.destination = self.root / image.RETAINED_NAME
        self.source = jpeg(929981)
        self.original.write_bytes(self.source)
        self.original_inode = self.original.stat().st_ino
        self.calls = []
        self.sizes = {65: 460000, 45: 338379, 30: 250000}
        self.properties = 'format: jpeg\npixelWidth: 3840\npixelHeight: 2160\nhasAlpha: no\n'
        self.block = patch.object(image, 'blocked', return_value=False)
        self.block.start(); self.addCleanup(self.block.stop)
        self.mark = patch.object(image, 'mark_unconfirmed')
        self.marked = self.mark.start(); self.addCleanup(self.mark.stop)

    def runner(self, args, seconds, **kwargs):
        self.calls.append((args, seconds, kwargs))
        operation = {'command': args, 'state': 'completed', 'exit': 0, 'cleanup_confirmed': True}
        if '-g' in args:
            return 0, self.properties, operation
        quality = int(args[6])
        self.assertNotEqual(Path(args[7]), self.original)
        self.assertEqual(Path(args[7]).read_bytes(), self.source)
        Path(args[-1]).write_bytes(jpeg(self.sizes[quality], b'z'))
        return 0, '', operation

    def retain(self, runner=None):
        return image.retain_store_image(self.original, self.destination, runner or self.runner)

    def failure_receipt(self):
        path = self.root / image.FAILURE_NAME
        self.assertTrue(path.is_file()); self.assertFalse(path.is_symlink())
        self.assertEqual(path.stat().st_nlink, 1)
        raw = path.read_bytes()
        self.assertLessEqual(len(raw), 64 * 1024)
        self.assertEqual(list(self.root.glob('.vision-store-receipt-*')), [])
        value = json.loads(raw)
        self.assertFalse(value['success'])
        self.assertEqual(value['source_file'], image.ORIGINAL_NAME)
        self.assertEqual(value['source_sha256'], hashlib.sha256(self.source).hexdigest())
        self.assertEqual(value['source_bytes'], len(self.source))
        return value

    def assert_preserved(self):
        self.assertEqual(self.original.read_bytes(), self.source)
        self.assertEqual(self.original.stat().st_ino, self.original_inode)
        self.assertEqual(self.original.stat().st_nlink, 1)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob('.vision-store-image-*')), [])

    def test_native_observed_size_contract_keeps_raw_and_full_resolution_candidate(self):
        result = self.retain()
        self.assertEqual(result['source_bytes'], 929981)
        self.assertEqual(result['retained_bytes'], 338379)
        self.assertEqual(result['quality'], 45)
        self.assertEqual(result['dimensions'], [3840, 2160])
        self.assertFalse(result['has_alpha']); self.assertFalse(result['resized']); self.assertFalse(result['cropped'])
        self.assertTrue(result['source_retained'])
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.source).hexdigest())
        self.assertEqual(result['retained_sha256'], hashlib.sha256(self.destination.read_bytes()).hexdigest())
        self.assertEqual(self.original.read_bytes(), self.source)
        self.assertEqual(self.original.stat().st_ino, self.original_inode)
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.assertEqual([int(c[0][6]) for c in self.calls if '-s' in c[0]], [65, 45])
        self.assertNotIn('-Z', [arg for c in self.calls for arg in c[0]])
        self.assertEqual([c[1] for c in self.calls], [5, 10, 5, 10, 5])
        self.assertEqual(list(self.root.glob('.vision-store-image-*')), [])

    def test_small_jpeg_retains_original_bytes_without_reencoding(self):
        self.source = jpeg(450000); self.original.write_bytes(self.source)
        result = self.retain()
        self.assertIsNone(result['quality']); self.assertEqual(result['encoding'], 'original JPEG bytes')
        self.assertEqual(self.destination.read_bytes(), self.source)
        self.assertEqual(result['source_sha256'], result['retained_sha256'])
        self.assertEqual(len(self.calls), 1)

    def test_three_quality_attempt_limit_failure_keeps_original(self):
        self.sizes = dict.fromkeys(image.QUALITIES, 460000)
        with self.assertRaisesRegex(ValueError, 'cap'): self.retain()
        self.assertEqual(len(self.calls), 7)
        self.assert_preserved()

    def test_wrong_dimensions_format_alpha_missing_or_duplicate_metadata_fail_closed(self):
        good = self.properties
        for bad in [good.replace('3840', '1440'), good.replace('jpeg', 'png'), good.replace('no', 'yes'),
                    good.replace('hasAlpha: no\n', ''), good + 'pixelWidth: 3840\n']:
            self.properties = bad
            with self.subTest(properties=bad), self.assertRaises(ValueError): self.retain()
            self.assert_preserved()

    def test_encoded_property_change_never_qualifies(self):
        def runner(args, seconds, **kwargs):
            result = self.runner(args, seconds, **kwargs)
            if '-g' in args and Path(args[-1]) != self.original:
                return result[0], self.properties.replace('2160', '1080'), result[2]
            return result
        with self.assertRaisesRegex(ValueError, 'dimensions'): self.retain(runner)
        self.assert_preserved()

    def test_nonzero_encoder_never_retried(self):
        def runner(args, seconds, **kwargs):
            if '-s' in args:
                self.calls.append((args, seconds, kwargs))
                return 13, 'sips: synthetic encoder refusal\n', {'state': 'completed', 'exit': 13, 'cleanup_confirmed': True}
            return self.runner(args, seconds, **kwargs)
        with self.assertRaisesRegex(ValueError, 'failed'): self.retain(runner)
        self.assertEqual(len(self.calls), 2); self.assert_preserved(); self.marked.assert_not_called()
        receipt = self.failure_receipt()
        self.assertEqual(receipt['stage'], 'encode_quality_65')
        self.assertEqual(receipt['attempted_qualities'], [65])
        self.assertEqual(receipt['operations'][-1]['command'], self.calls[-1][0])
        self.assertEqual(receipt['operations'][-1]['exit'], 13)
        self.assertEqual(receipt['operations'][-1]['returned_exit'], 13)
        self.assertEqual(receipt['operations'][-1]['quality'], 65)
        self.assertEqual(receipt['operations'][-1]['output_tail'], 'sips: synthetic encoder refusal\n')

    def test_timeout_output_limit_or_cleanup_uncertainty_stops_no_fallback(self):
        for code, state, clean in [(124, 'timed_out', True), (125, 'output_limit', True),
                                   (126, 'cleanup_unconfirmed', False), (0, 'completed', False), (0, 'started', True)]:
            self.calls.clear(); self.marked.reset_mock()
            (self.root / image.FAILURE_NAME).unlink(missing_ok=True)
            def runner(args, seconds, **kwargs):
                if '-s' in args:
                    self.calls.append((args, seconds, kwargs))
                    Path(args[-1]).write_bytes(jpeg(100))
                    return code, 'synthetic command uncertainty\n', {'state': state, 'exit': code, 'cleanup_confirmed': clean}
                return self.runner(args, seconds, **kwargs)
            with self.subTest(code=code, state=state, clean=clean), self.assertRaises(ValueError): self.retain(runner)
            self.assertEqual(len(self.calls), 2); self.assert_preserved(); self.marked.assert_called_once()
            receipt = self.failure_receipt(); operation = receipt['operations'][-1]
            self.assertEqual(receipt['attempted_qualities'], [65])
            self.assertEqual(operation['exit'], code); self.assertEqual(operation['state'], state)
            self.assertEqual(operation['cleanup_confirmed'], clean)
            self.assertEqual(operation['output_tail'], 'synthetic command uncertainty\n')

    def test_barrier_blocks_before_any_host_command(self):
        with patch.object(image, 'blocked', return_value=True), self.assertRaisesRegex(ValueError, 'barrier'):
            self.retain()
        self.assertFalse(self.calls); self.assert_preserved()

    def test_existing_or_symlink_destination_is_not_overwritten(self):
        self.destination.write_bytes(b'existing')
        with self.assertRaisesRegex(ValueError, 'collision'): self.retain()
        self.assertEqual(self.destination.read_bytes(), b'existing')
        self.destination.unlink(); self.destination.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'collision'): self.retain()
        self.assertTrue(self.destination.is_symlink()); self.assertFalse(self.calls)

    def test_symlink_and_hardlink_source_are_rejected_without_mutation(self):
        renamed = self.root / 'raw.jpg'; self.original.rename(renamed)
        self.original.symlink_to(renamed)
        with self.assertRaises(ValueError): self.retain()
        self.original.unlink(); self.original.hardlink_to(renamed)
        with self.assertRaises(ValueError): self.retain()
        self.assertEqual(renamed.read_bytes(), self.source); self.assertFalse(self.calls)

    def test_ancestor_symlink_and_noncanonical_or_wrong_names_rejected(self):
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        for original, destination in [(alias / image.ORIGINAL_NAME, alias / image.RETAINED_NAME),
                                      (Path(image.ORIGINAL_NAME), Path(image.RETAINED_NAME)),
                                      (self.original, self.root / 'other.jpg'),
                                      (self.root / '..' / self.root.name / image.ORIGINAL_NAME, self.destination)]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                image.retain_store_image(original, destination, self.runner)
        self.assertFalse(self.calls)

    def test_empty_oversize_or_incomplete_jpeg_rejected_before_metadata(self):
        for data in [b'', jpeg(image.MAX_SOURCE_BYTES + 1), b'not jpeg', b'\xff\xd8partial']:
            self.original.write_bytes(data)
            with self.subTest(size=len(data)), self.assertRaises(ValueError): self.retain()
            self.assertEqual(self.original.read_bytes(), data)
        self.assertFalse(self.calls)

    def test_encoded_symlink_hardlink_or_incomplete_jpeg_fails_preserving_raw(self):
        for mode in ['symlink', 'hardlink', 'partial']:
            def runner(args, seconds, **kwargs):
                if '-s' in args:
                    target = Path(args[-1])
                    if mode == 'symlink': target.symlink_to(self.original)
                    elif mode == 'hardlink': target.hardlink_to(Path(args[7]))
                    else: target.write_bytes(b'\xff\xd8partial')
                    return 0, '', {'state': 'completed', 'exit': 0, 'cleanup_confirmed': True}
                return self.runner(args, seconds, **kwargs)
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.retain(runner)
            self.assert_preserved()

    def test_concurrent_destination_is_never_overwritten(self):
        link = os.link
        def publish(source, destination, **kwargs):
            self.destination.write_bytes(b'concurrent')
            return link(source, destination, **kwargs)
        with patch.object(image.os, 'link', side_effect=publish), self.assertRaises(FileExistsError): self.retain()
        self.assertEqual(self.destination.read_bytes(), b'concurrent')
        self.assertEqual(self.original.read_bytes(), self.source)
        self.assertEqual(list(self.root.glob('.vision-store-image-*')), [])

    def test_external_source_change_during_metadata_never_qualifies(self):
        changed = jpeg(len(self.source), b'y')
        def runner(args, seconds, **kwargs):
            result = self.runner(args, seconds, **kwargs)
            self.original.write_bytes(changed)
            return result
        with self.assertRaisesRegex(ValueError, 'Original screenshot changed'): self.retain(runner)
        self.assertEqual(self.original.read_bytes(), changed)
        self.assertFalse(self.destination.exists())
        self.assertEqual(len(self.calls), 1)

    def test_real_disposable_python_timeout_retains_original_and_stops(self):
        # Exercise the unchanged process-group runner with Python, never sips,
        # simctl, Xcode, or another native tool.
        from watch_process import execute as bounded_execute
        operations = []
        def runner(args, seconds, **kwargs):
            if '-s' in args:
                result = bounded_execute([sys.executable, '-c',
                    'import time; print("portable child", flush=True); time.sleep(3)'],
                    0.05, **kwargs)
                operations.append(result[2])
                return result
            return self.runner(args, seconds, **kwargs)
        with self.assertRaisesRegex(ValueError, 'timed out'): self.retain(runner)
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['exit'], 124)
        self.assertTrue(operations[0]['cleanup_confirmed'])
        self.assertEqual(operations[0]['state'], 'timed_out')
        self.assert_preserved(); self.marked.assert_called_once()
        receipt = self.failure_receipt(); command = receipt['operations'][-1]
        self.assertEqual(command['exit'], 124)
        self.assertEqual(command['executed_command'], operations[0]['command'])
        self.assertIn('portable child', command['output_tail'])

    def test_missing_encoder_output_preserves_raw(self):
        def runner(args, seconds, **kwargs):
            if '-s' in args:
                return 0, '', {'state': 'completed', 'exit': 0, 'cleanup_confirmed': True}
            return self.runner(args, seconds, **kwargs)
        with self.assertRaises(FileNotFoundError): self.retain(runner)
        self.assert_preserved()

    def test_default_adapter_calls_mature_bounded_runner(self):
        with patch.object(image, 'execute', side_effect=self.runner) as execute:
            result = image.retain_store_image(self.original, self.destination)
        self.assertEqual(result['quality'], 45)
        self.assertEqual(execute.call_count, 5)
        for call in execute.call_args_list:
            self.assertEqual(call.kwargs, {'output_limit': 65536, 'tail_limit': 8192, 'echo': False})

    def test_runner_exception_latches_before_diagnostics_and_blocks_next_command(self):
        stopped = [False]
        commands = []
        failure = OSError('synthetic runner failure after child launch')
        def runner(args, seconds, **kwargs):
            commands.append(args)
            raise failure
        def latch(operation):
            self.assertEqual(operation, {'state': 'vision_store_image_runner_exception',
                                         'exit': 126, 'cleanup_confirmed': False})
            stopped[0] = True
        write_failure = image._write_failure
        def persist(folder, context, error):
            self.assertTrue(stopped[0], 'Uncertainty must latch before diagnostics')
            return write_failure(folder, context, error)
        with patch.object(image, 'blocked', side_effect=lambda args=None: stopped[0]), \
             patch.object(image, 'mark_unconfirmed', side_effect=latch) as marked, \
             patch.object(image, '_write_failure', side_effect=persist):
            with self.assertRaises(OSError) as raised: self.retain(runner)
            self.assertIs(raised.exception, failure)
            receipt = self.failure_receipt(); row = receipt['operations'][0]
            self.assertEqual(receipt['stage'], 'source_metadata')
            self.assertEqual(row['command'], commands[0])
            self.assertEqual(row['state'], 'runner_exception')
            self.assertIsNone(row['exit'])
            self.assertFalse(row['cleanup_confirmed'])
            self.assertEqual(row['uncertainty_barrier'], {'state': 'vision_store_image_runner_exception',
                                                         'exit': 126, 'cleanup_confirmed': False})
            self.assertEqual(row['error_type'], 'OSError')
            self.assertEqual(row['error'], str(failure))
            original_receipt = (self.root / image.FAILURE_NAME).read_bytes()
            with self.assertRaisesRegex(ValueError, 'barrier'): self.retain(runner)
            self.assertEqual(len(commands), 1)
            self.assertEqual((self.root / image.FAILURE_NAME).read_bytes(), original_receipt)
            marked.assert_called_once()
        self.assert_preserved()

    def test_metadata_validation_failure_durably_keeps_full_metadata_tail(self):
        self.properties = self.properties.replace('3840', '1440')
        with self.assertRaisesRegex(ValueError, 'dimensions'): self.retain()
        receipt = self.failure_receipt()
        self.assertEqual(receipt['stage'], 'source_metadata')
        self.assertEqual(receipt['attempted_qualities'], [])
        self.assertEqual(len(receipt['operations']), 1)
        self.assertEqual(receipt['operations'][0]['command'], self.calls[0][0])
        self.assertEqual(receipt['operations'][0]['output_tail'], self.properties)
        self.assertEqual(receipt['operations'][0]['exit'], 0)
        self.assert_preserved()

    def test_metadata_command_failure_keeps_exit_and_error_output(self):
        def runner(args, seconds, **kwargs):
            return 7, 'sips could not read JPEG: synthetic diagnostic', {
                'command': args, 'state': 'completed', 'exit': 7, 'cleanup_confirmed': True}
        with self.assertRaisesRegex(ValueError, 'command failed'): self.retain(runner)
        receipt = self.failure_receipt()
        self.assertEqual(receipt['stage'], 'source_metadata')
        self.assertEqual(receipt['operations'][0]['exit'], 7)
        self.assertEqual(receipt['operations'][0]['output_tail'], 'sips could not read JPEG: synthetic diagnostic')
        self.assert_preserved()

    def test_failure_receipt_never_overwrites_existing_or_symlink_file(self):
        path = self.root / image.FAILURE_NAME
        path.write_text('original receipt')
        self.properties = self.properties.replace('3840', '1440')
        with self.assertRaisesRegex(ValueError, 'dimensions') as raised: self.retain()
        self.assertEqual(path.read_text(), 'original receipt')
        self.assertIn('receipt', ' '.join(getattr(raised.exception, '__notes__', [])))
        path.unlink(); path.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'dimensions'): self.retain()
        self.assertTrue(path.is_symlink()); self.assertFalse((self.root / 'missing').exists())
        self.assert_preserved()

    def test_receipt_write_failure_does_not_mask_original_failure(self):
        self.properties = self.properties.replace('3840', '1440')
        with patch.object(image.tempfile, 'mkstemp', side_effect=OSError('synthetic disk full')):
            with self.assertRaisesRegex(ValueError, 'dimensions') as raised: self.retain()
        self.assertIn('disk full', ' '.join(getattr(raised.exception, '__notes__', [])))
        self.assertFalse((self.root / image.FAILURE_NAME).exists()); self.assert_preserved()

    def test_receipt_tail_bound_preserves_exact_exit_and_last_diagnostic(self):
        text = '\x01' * 60000 + 'last diagnostic'
        def runner(args, seconds, **kwargs):
            if '-s' in args:
                return 19, text, {'command': args, 'state': 'completed', 'exit': 19, 'cleanup_confirmed': True,
                                  'output_bytes': len(text)}
            return self.runner(args, seconds, **kwargs)
        with self.assertRaisesRegex(ValueError, 'command failed'): self.retain(runner)
        receipt = self.failure_receipt(); row = receipt['operations'][-1]
        self.assertEqual(row['exit'], 19); self.assertEqual(row['returned_output_bytes'], len(text))
        self.assertEqual(row['output_bytes'], len(text)); self.assertTrue(row['output_tail_truncated'])
        self.assertTrue(row['output_tail'].endswith('last diagnostic'))
        self.assertLessEqual(len(image._json_bytes(row)), image.OPERATION_LIMIT + 64)
        self.assert_preserved()

    def test_seven_escaped_output_receipts_fit_64_kib_failure_bound(self):
        self.sizes = dict.fromkeys(image.QUALITIES, 460000)
        def runner(args, seconds, **kwargs):
            code, text, operation = self.runner(args, seconds, **kwargs)
            return code, text + '\x01' * 60000 + 'tail marker', operation
        with self.assertRaisesRegex(ValueError, 'candidate evidence cap'): self.retain(runner)
        receipt = self.failure_receipt()
        self.assertEqual(len(receipt['operations']), 7)
        self.assertEqual(receipt['attempted_qualities'], [65, 45, 30])
        for row in receipt['operations']:
            self.assertTrue(row['output_tail'].endswith('tail marker'))
            self.assertTrue(row['output_tail_truncated'])
        self.assert_preserved()

    def test_success_proof_keeps_exact_bounded_command_output_receipts(self):
        proof = self.retain()
        self.assertFalse((self.root / image.FAILURE_NAME).exists())
        self.assertEqual(len(proof['operations']), 5)
        self.assertEqual(proof['operations'][0]['output_tail'], self.properties)
        self.assertEqual(proof['operations'][1]['quality'], 65)
        self.assertEqual(proof['operations'][3]['quality'], 45)
        for row, call in zip(proof['operations'], self.calls):
            self.assertEqual(row['command'], call[0]); self.assertEqual(row['exit'], 0)
            self.assertEqual(row['returned_exit'], 0); self.assertTrue(row['cleanup_confirmed'])

    def test_phase_clock_rejects_invalid_or_insufficient_deadline_without_commands(self):
        now = time.monotonic()
        for deadline in [float('nan'), float('inf'), True, now - 1, now + 81, now + 5]:
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                image.retain_store_image(self.original, self.destination, self.runner, deadline=deadline)
            self.assert_preserved()
        self.assertFalse(self.calls)

    def test_late_success_is_not_accepted_or_retried(self):
        clock = [100.0]
        def runner(args, seconds, **kwargs):
            result = self.runner(args, seconds, **kwargs)
            clock[0] = 181
            return result
        with patch.object(image.time, 'monotonic', side_effect=lambda: clock[0]), self.assertRaises(ValueError):
            self.retain(runner)
        self.assertEqual(len(self.calls), 1); self.assert_preserved(); self.marked.assert_called_once()


if __name__ == '__main__': unittest.main()
