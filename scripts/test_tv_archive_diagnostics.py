"""Synthetic local archive diagnostic tests; never native commands or uploads."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tv_archive_diagnostics as diag
import tv_release_archive as archive
from test_tv_release_archive import ArchiveFixture, environment


class DiagnosticTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return ArchiveFixture(Path(temp.name))

    def test_inventory_is_complete_before_unknown_entry_rejects_and_never_reads_its_payload(self):
        f=self.fixture();p=f.archive/'Products/usr/local/lib/Unknown.a';p.parent.mkdir(parents=True)
        p.write_bytes(b'PRIVATE_UNEXPECTED_PAYLOAD')
        second=f.archive/'UnknownRoot.txt';second.write_bytes(b'PRIVATE_UNEXPECTED_PAYLOAD')
        result=diag.collect(f.archive,100,clock=lambda:0)
        rows={x['path']:x for x in result['inventory']['entries']}
        self.assertTrue(result['inventory']['complete'])
        self.assertEqual(rows['Products/usr/local/lib/Unknown.a']['size'],len(b'PRIVATE_UNEXPECTED_PAYLOAD'))
        self.assertEqual(rows['UnknownRoot.txt']['type'],'file')
        self.assertNotIn('PRIVATE_UNEXPECTED_PAYLOAD',json.dumps(result))
        self.assertFalse(result['inventory']['content_read'])
        with self.assertRaisesRegex(archive.Rejected,'unexpected-archive-entry') as caught:f.verify()
        offending=caught.exception.offending_entry
        self.assertIn(offending['path'],rows)
        self.assertEqual(offending,rows[offending['path']])
        self.assertEqual(f.calls,[])

    def test_unknown_or_allowed_symlink_targets_are_never_followed(self):
        f=self.fixture();outside=f.root/'external';outside.mkdir();(outside/'private.txt').write_text('PRIVATE_TARGET')
        (f.archive/'UnknownLink').symlink_to(outside,target_is_directory=True)
        (f.app/'Info.plist').unlink();(f.app/'Info.plist').symlink_to(outside/'private.txt')
        value=diag.collect(f.archive,100,clock=lambda:0)
        rows={x['path']:x for x in value['inventory']['entries']}
        self.assertEqual(rows['UnknownLink']['type'],'symlink')
        self.assertFalse(any(x.startswith('UnknownLink/') for x in rows))
        self.assertEqual(value['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')
        self.assertNotIn('PRIVATE_TARGET',json.dumps(value))
        with self.assertRaises(ValueError):diag.safe_read(f.archive,'UnknownLink/private.txt',100,clock=lambda:0)

    def test_fixed_pure_file_metadata_continues_despite_unknown_entries_and_metadata_mismatch(self):
        f=self.fixture();(f.archive/'Unknown').write_bytes(b'ignored')
        f.package.metadata['UIDeviceFamily']=[1,2];f.package.write_info()
        result=diag.collect(f.archive,100,clock=lambda:0)
        self.assertTrue(result['inventory']['complete'])
        facts=result['fixed_files']
        self.assertFalse(facts['qualifying']);self.assertFalse(facts['external_commands'])
        self.assertFalse(facts['app_metadata_comparisons']['UIDeviceFamily']['matches'])
        self.assertTrue(facts['app_metadata_comparisons']['CFBundleIdentifier']['matches'])
        self.assertEqual(facts['files'][diag.APP+'/QRCatcherTV']['mach_header']['build'][0]['platform'],3)
        self.assertEqual(facts['files'][diag.DSYM+'/Contents/Info.plist']['status'],'observed')
        self.assertEqual(f.calls,[])

    def test_photos_add_usage_description_is_observed_without_a_diagnostic_gate(self):
        key='NSPhotoLibraryAddUsageDescription'
        for description in ('Save the QR image you explicitly choose to your photo library.', 'different copy', None):
            f=self.fixture()
            if description is None:f.package.metadata.pop(key, None)
            else:f.package.metadata[key]=description
            f.package.write_info()
            result=diag.collect(f.archive,100,clock=lambda:0)
            facts=result['fixed_files'];observation=facts['files'][diag.APP+'/Info.plist']
            with self.subTest(description=description):
                self.assertEqual(observation['status'],'observed')
                self.assertEqual(observation['metadata'].get(key),description)
                self.assertEqual(key in observation['metadata'],description is not None)
                self.assertFalse(facts['qualifying']);self.assertFalse(facts['external_commands'])
                self.assertNotIn(key,facts['app_metadata_comparisons'])
                self.assertEqual(f.calls,[])

    def test_inventory_limits_keep_collected_entries_and_never_claim_completeness(self):
        f=self.fixture()
        with patch.object(diag,'MAX_ENTRIES',3):value=diag.inventory(f.archive,100,clock=lambda:0)
        self.assertEqual(len(value['entries']),3);self.assertFalse(value['complete'])
        self.assertEqual(value['failure']['reason'],'diagnostic-inventory-limit')
        value=diag.inventory(f.archive,0,clock=lambda:0)
        self.assertEqual(value['entries'],[]);self.assertFalse(value['complete'])
        self.assertEqual(value['failure']['reason'],'diagnostic-deadline')

    def test_hardlink_fifo_and_oversize_fixed_file_are_metadata_only(self):
        for kind in ('hardlink','fifo','oversize'):
            f=self.fixture();p=f.app/'Info.plist';p.unlink()
            if kind=='hardlink':os.link(f.app/'PrivacyInfo.xcprivacy',p)
            elif kind=='fifo':os.mkfifo(p)
            else:
                with p.open('wb') as stream:stream.truncate(diag.MAX_FILE_BYTES+1)
            result=diag.collect(f.archive,100,clock=lambda:0)
            with self.subTest(kind=kind):self.assertEqual(result['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')

    def test_diagnostic_malformed_plist_and_mach_headers_do_not_abort_other_fields(self):
        f=self.fixture();(f.app/'Info.plist').write_bytes(b'invalid');(f.app/'QRCatcherTV').write_bytes(b'invalid')
        result=diag.collect(f.archive,100,clock=lambda:0)['fixed_files']['files']
        self.assertEqual(result[diag.APP+'/Info.plist']['status'],'unavailable')
        self.assertEqual(result[diag.APP+'/QRCatcherTV']['status'],'unavailable')
        self.assertEqual(result[diag.APP+'/PrivacyInfo.xcprivacy']['status'],'observed')
        f=self.fixture();f.package.metadata['CFBundleVersion']=float('nan');f.package.write_info()
        value=diag.collect(f.archive,100,clock=lambda:0)
        self.assertEqual(value['fixed_files']['files'][diag.APP+'/Info.plist']['status'],'unavailable')
        json.dumps(value,allow_nan=False)

    def test_report_size_fallback_preserves_original_offending_entry_and_diagnostics(self):
        failure={'phase':'proof','type':'Rejected','reason':'unexpected-archive-entry','offending_entry':{'path':'Products/usr','type':'directory','size':96}}
        observation={'inventory':{'entries':[failure['offending_entry']],'complete':True},'fixed_files':{'qualifying':False}}
        value={'schema':1,'qualified':False,'signing_qualified':False,'store_qualified':False,
               'older_os_qualified':False,'ui_qualification_separate':True,'failure':failure,
               'archive_diagnostic':observation,'oversized':'x'*archive.MAX_REPORT}
        report=json.loads(archive.report_bytes(value))
        self.assertEqual(report['failure'],failure);self.assertEqual(report['archive_diagnostic'],observation)
        self.assertEqual(report['retention_failure']['reason'],'report-byte-limit')
        self.assertFalse(report['qualified'])

    def test_execute_failure_keeps_all_safe_observations_without_external_validation_commands(self):
        f=self.fixture();(f.archive/'UnknownRoot').write_text('unknown');calls=[]
        def run(argv,**kwargs):
            calls.append(argv)
            if argv==archive.ARCHIVE_COMMAND:shutil.copytree(f.archive,f.root/archive.ARCHIVE)
            data=(b'Xcode 27.0\nBuild version 27A266a\n' if argv==['xcodebuild','-version'] else b'appletvos27.0\n')
            return subprocess.CompletedProcess(argv,0,data,b'')
        with patch.object(archive,'source_identity',return_value={'source':'synthetic'}):
            result=archive.execute(env=environment(),root=f.root,clock=lambda:0,runner=run)
        self.assertFalse(result['qualified']);self.assertEqual(result['failure']['reason'],'unexpected-archive-entry')
        self.assertEqual(result['failure']['offending_entry']['path'],'UnknownRoot')
        self.assertTrue(result['archive_diagnostic']['inventory']['complete'])
        self.assertTrue(result['archive_diagnostic']['fixed_files']['app_metadata_comparisons']['CFBundleIdentifier']['matches'])
        self.assertEqual(calls.count(archive.ARCHIVE_COMMAND),1)
        self.assertFalse(any(a[:2]==['xcrun','assetutil'] or a[:2]==['xcrun','dwarfdump'] for a in calls))

    def test_root_symlink_and_unlisted_reads_reject_without_traversal(self):
        f=self.fixture();link=f.root/'alias';link.symlink_to(f.archive,target_is_directory=True)
        result=diag.inventory(link,100,clock=lambda:0)
        self.assertFalse(result['complete']);self.assertEqual(result['entries'],[])
        with self.assertRaises(ValueError):diag.safe_read(f.archive,'../outside',100,clock=lambda:0)


if __name__=='__main__':unittest.main()
