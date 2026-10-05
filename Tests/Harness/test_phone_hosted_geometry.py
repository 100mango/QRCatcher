"""Executable bounded diagnostic collectors and source contracts, not native proof."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import export_phone_hosted_geometry as collector
import diagnostic_phone_hosted_route as route

DEVICE = '11111111-1111-4111-8111-111111111111'


def rect():
    return dict(x=0.125, y=1.25, width=319.875, height=44.125,
                min_x=0.125, min_y=1.25, max_x=320, max_y=45.375)


def traits():
    return dict(content_size_category='UICTContentSizeCategoryAccessibilityXXXL', display_scale=3,
                horizontal_size_class=1, vertical_size_class=1, idiom=0, layout_direction=0)


def view(scroll=False):
    value = dict(frame=rect(), bounds=rect(), in_root=rect(),
                 safe_area_insets=dict(top=0, left=0, bottom=0, right=0), traits=traits(),
                 window_attached=False, superview_present=True, ambiguous_layout=False,
                 hidden=False, in_window=None, window_bounds=None)
    if scroll:
        value['scroll'] = dict(content_size=dict(width=319.875, height=10000.125),
                              content_offset=dict(x=0.125, y=9956.0),
                              content_inset=dict(top=0, left=0, bottom=0, right=0),
                              adjusted_content_inset=dict(top=0, left=0, bottom=0, right=0),
                              indicator_inset=dict(top=0, left=0, bottom=0, right=0),
                              inset_adjustment_behavior=0, zoom_scale=1, scroll_enabled=True)
    return value


def font():
    return dict(font_name='.SFUI-Regular', point_size=53, line_height=63.28125, ascender=50.1,
                descender=-12.0, leading=1.18125, number_of_lines=0, line_break_mode=5, adjusts_for_category=True)


def receipt(key):
    kind, width, height, stage = key
    payload = collector.PAYLOADS[kind]
    return dict(version=1, observations_qualify_pass=False, fixture=collector.FIXTURE,
                payload_kind=kind, payload_utf16_length=len(payload.encode('utf-16-le')) // 2,
                payload_utf8_bytes=len(payload.encode()), viewport=dict(width=width, height=height),
                stage=stage, target=rect(), full_text_size_that_fits=dict(width=319.875, height=10000.125),
                current_action_title_size_that_fits=dict(width=319.875, height=80.5),
                host=view(), result=view(), host_traits=traits(), result_traits=traits(), parent_is_host=True,
                presented=False, text=view(True), actions=view(True), body=view(), title=view(),
                body_font=font(), title_font=font(),
                buttons=[dict(identifier=name, view=view(), in_actions=rect(), title_label=view(), font=font())
                         for name in collector.ACTIONS[kind]])


def operation():
    return dict(command=collector.expected_command(DEVICE), timeout_seconds=855, state='completed', exit=65,
                cleanup_confirmed=True, elapsed_seconds=60.0, output_bytes=900)


def summary():
    now = time.time()
    return dict(result='Failed', totalTestCount=30, passedTests=29, failedTests=1, skippedTests=0,
                expectedFailures=0, devicesAndConfigurations=[dict(device=dict(deviceId=DEVICE, platform='iOS Simulator'))],
                startTime=now-60, finishTime=now-1,
                testFailures=[dict(testIdentifierString=collector.TEST, failureText='unchanged containment failed')])


class PhoneHostedGeometryTests(unittest.TestCase):
    def test_all_eight_combinations_and44_stages_accept_precise_observations_without_qualification(self):
        self.assertEqual(len(collector.expected_keys()), 44)
        for key in collector.expected_keys():
            parsed_key, value = collector.receipt(json.dumps(receipt(key)).encode())
            self.assertEqual(parsed_key, key)
            self.assertEqual(value['body']['bounds']['width'], 319.875)
            self.assertFalse(value['observations_qualify_pass'])
            self.assertLess(len(json.dumps(value).encode()), collector.RECEIPT_LIMIT)

    def test_observed_oversize_unattached_stale_or_rounding_is_retained_without_judging_pass(self):
        value = receipt(('text',320,568,'ending'))
        value['target']['height'] = 12345.5
        value['text']['scroll']['content_offset']['y'] = 0.000001
        value['result']['ambiguous_layout'] = True
        self.assertEqual(collector.receipt(json.dumps(value).encode())[1], value)

    def test_schema_versions_flags_content_and_lengths_fail_closed(self):
        original = receipt(('text',320,568,'ending'))
        for key, value in [('version',True),('version',2),('observations_qualify_pass',True),
                           ('payload_kind','decoded'),('payload_utf16_length',True),
                           ('payload_utf8_bytes',1),('stage','copy'),('payload','sensitive decoded text')]:
            changed=copy.deepcopy(original);changed[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):collector.receipt(json.dumps(changed).encode())
        del original['body_font']
        with self.assertRaises(ValueError):collector.receipt(json.dumps(original).encode())

    def test_oversized_duplicate_nonfinite_and_numeric_boolean_json_reject(self):
        with self.assertRaises(ValueError):collector.receipt(b' '*16385)
        with self.assertRaises(ValueError):collector.strict_json('{"version":1,"version":1}')
        for value in [float('nan'),float('inf'), True, -1, 1e10]:
            row=receipt(('text',320,568,'ending'));row['viewport']['width']=value
            with self.subTest(value=value),self.assertRaises(ValueError):collector.receipt(json.dumps(row).encode())

    def test_window_action_font_and_scroll_shapes_reject(self):
        for mutate in [lambda r:r['body'].update(window_attached=True),
                       lambda r:r['buttons'][0].update(identifier='history.result.open'),
                       lambda r:r['buttons'].append(r['buttons'][0]),
                       lambda r:r['body_font'].update(point_size='53'),
                       lambda r:r['text']['scroll'].update(content='decoded'),
                       lambda r:r['actions'].pop('scroll')]:
            row=receipt(('text',320,568,'ending'));mutate(row)
            with self.assertRaises(ValueError):collector.receipt(json.dumps(row).encode())

    def test_exact_finalized_hosted_command_rejects_timeout_uncertainty_wrong_device_selector_or_duplicate(self):
        def log(op):return ('BOUNDED_COMMAND_END '+json.dumps(op)+'\n').encode()
        self.assertEqual(collector.finalized_command(log(operation()),DEVICE),operation())
        for key,value in [('exit',124),('exit',True),('state','timed_out'),('cleanup_confirmed',False),
                          ('timeout_seconds',856),('elapsed_seconds',861),('command',['echo','fake'])]:
            op=operation();op[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):collector.finalized_command(log(op),DEVICE)
        with self.assertRaises(ValueError):collector.finalized_command(log(operation())*2,DEVICE)
        with self.assertRaises(ValueError):collector.finalized_command(log(operation()),'wrong')

    def test_complete30_failed_or_passed_summary_keeps_original_outcome(self):
        self.assertEqual(collector.validate_summary(summary(),operation(),DEVICE)['result'],'Failed')
        value=summary();value.update(result='Passed',passedTests=30,failedTests=0);op=operation();op['exit']=0
        self.assertEqual(collector.validate_summary(value,op,DEVICE)['result'],'Passed')

    def test_summary_partial_wrong_device_stale_counts_or_skip_reject(self):
        for key,value in [('totalTestCount',29),('passedTests',True),('failedTests',0),('skippedTests',1),
                          ('expectedFailures',1),('result','Passed'),('finishTime',time.time()-500),
                          ('startTime',None),('devicesAndConfigurations',[])]:
            row=summary();row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):collector.validate_summary(row,operation(),DEVICE)

    def environment(self):
        return dict(GITHUB_SHA='a'*40,GITHUB_WORKFLOW_SHA='a'*40,GITHUB_REPOSITORY=route.REPOSITORY,
                    GITHUB_REF=route.REF,GITHUB_WORKFLOW_REF=route.WORKFLOW_REF,GITHUB_EVENT_NAME='push',
                    DIAGNOSTIC_ONLY='true',RUNNER_OS='macOS',RUNNER_ARCH='ARM64',GITHUB_JOB='platform',
                    EVIDENCE_SCOPE='iphone_pro',GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',SIMULATOR_ID=DEVICE)

    @contextlib.contextmanager
    def checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path.cwd();root=Path(temp).resolve();os.chdir(root)
            try:
                (root/'.github/workflows').mkdir(parents=True)
                for name in [route.CANONICAL,route.WORKFLOW]:(root/name).write_bytes((ROOT/name).read_bytes())
                env=self.environment();env['GITHUB_ENV']=str(root/'runner-env')
                with patch.dict(os.environ,env,clear=True),patch.object(route,'source_readback',return_value='b'*40),contextlib.redirect_stdout(io.StringIO()):
                    route.main(['validate'])
                    collector.RESULT.mkdir();(collector.RESULT/'Info.plist').write_text('actual-hosted-result')
                    Path('ios-unit.log').write_text('BOUNDED_COMMAND_END '+json.dumps(operation())+'\n')
                    yield root
            finally:os.chdir(old)

    def export(self, suffix=False):
        collector.ATTACHMENTS.mkdir(parents=True)
        entries=[]
        for index,key in enumerate(sorted(collector.expected_keys())):
            name=collector.PREFIX+key[0]+'-'+str(key[1])+'x'+str(key[2])+'-'+key[3]
            if suffix:name+='_0_11111111-1111-4111-8111-111111111111.json'
            filename=str(index)+'.json';(collector.ATTACHMENTS/filename).write_text(json.dumps(receipt(key)))
            entries.append(dict(suggestedHumanReadableName=name,exportedFileName=filename))
        manifest=[dict(testIdentifier=collector.TEST+'()',attachments=entries)]
        (collector.ATTACHMENTS/'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_public_manifest44_complete_set_with_native_name_suffix(self):
        with self.checkout():
            for suffix in [False,True]:
                if collector.ATTACHMENTS.exists():
                    import shutil;shutil.rmtree(collector.ATTACHMENTS)
                rows=self.export(suffix)
                self.assertEqual(len(collector.collect_entries(rows)),44)

    def test_missing_duplicate_wrong_test_wrong_name_escape_or_tamper_reject(self):
        mutations=[lambda r:r[0]['attachments'].pop(),
                   lambda r:r[0]['attachments'].append(r[0]['attachments'][0]),
                   lambda r:r[0].update(testIdentifier='OtherTest/test'),
                   lambda r:r[0]['attachments'][0].update(suggestedHumanReadableName=collector.PREFIX+'wrong'),
                   lambda r:r[0]['attachments'][0].update(exportedFileName='../outside.json'),
                   lambda r:(collector.ATTACHMENTS/r[0]['attachments'][0]['exportedFileName']).write_text('{}')]
        for mutate in mutations:
            with self.checkout():
                rows=self.export();mutate(rows)
                with self.assertRaises(ValueError):collector.collect_entries(rows)

    def test_linked_oversized_attachment_and_result_symlink_fail_closed(self):
        for mode in ['symlink','hardlink','oversize','result-symlink']:
            with self.checkout() as root:
                rows=self.export();path=collector.ATTACHMENTS/'0.json'
                if mode=='symlink':path.rename('other.json');path.symlink_to(root/'other.json')
                if mode=='hardlink':os.link(path,root/'linked.json')
                if mode=='oversize':path.write_bytes(b' '*16385)
                if mode=='result-symlink':(collector.RESULT/'link').symlink_to(root/'other.json')
                with self.assertRaises(ValueError):
                    if mode=='result-symlink':collector.result_fingerprint()
                    else:collector.collect_entries(rows)

    def fake_execute(self,command,seconds,**options):
        self.assertFalse(any(word in command for word in ['simctl','xcodebuild']))
        op=dict(command=command,state='completed',cleanup_confirmed=True,exit=0)
        if 'summary' in command:return 0,json.dumps(summary()),op
        self.export(True)
        return 0,'',op

    def test_full_collector_keeps44_receipts_completed65_and_not_run_ui_without_device_operations(self):
        with self.checkout(),patch.object(collector,'execute',side_effect=self.fake_execute) as commands:
            self.assertEqual(collector.main(),0, (collector.OUT/'manifest.json').read_text())
            value=json.loads((collector.OUT/'manifest.json').read_text())
            self.assertEqual(value['hosted_outcome'],'Failed');self.assertEqual(value['hosted_operation']['exit'],65)
            self.assertEqual(len(value['receipts']),44);self.assertFalse(value['acceptance'])
            self.assertTrue(all(status=='NOT RUN' for status in value['phases'].values()))
            self.assertEqual(commands.call_count,2)
            self.assertFalse(value['fresh_source_readback_performed'])

    def test_result_mutation_rejects_before_copying_any_geometry(self):
        with self.checkout():
            def execute(*args,**kwargs):
                result=self.fake_execute(*args,**kwargs)
                if 'attachments' in args[0]:(collector.RESULT/'Info.plist').write_text('tampered')
                return result
            with patch.object(collector,'execute',side_effect=execute):self.assertEqual(collector.main(),1)
            self.assertEqual(list(collector.OUT.glob(collector.PREFIX+'*')),[])
            self.assertEqual(json.loads((collector.OUT/'manifest.json').read_text())['collection'],'REJECTED')

    def test_uncertainty_retention_process_free_and_never_accepts(self):
        for durable in [False,True]:
            with self.checkout() as root:
                if durable:(root/'build/owned-process-cleanup.json').write_text('{}')
                else:os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
                os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']=str(root/'build/owned-process-cleanup.json')
                with patch.object(collector,'execute',side_effect=AssertionError('no process')),patch.object(route,'source_readback',side_effect=AssertionError('no readback')):
                    self.assertEqual(collector.main(),0)
                value=json.loads((collector.OUT/'manifest.json').read_text())
                self.assertEqual(value['collection'],'NOT RUN: cleanup uncertainty');self.assertFalse(value['acceptance'])
                self.assertEqual(value['receipts'],[]);self.assertTrue(value['owned_cleanup_uncertainty_observed'])

    def test_executable_collector_uncertainty_uses_no_process_or_source_readback(self):
        with self.checkout() as root:
            env=dict(os.environ);env['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
            program=("import sys\nsys.path.insert(0,"+repr(str(ROOT/'scripts'))+")\n"
                     "import export_phone_hosted_geometry as c\n"
                     "def forbidden(*args, **kwargs):raise RuntimeError('process forbidden')\n"
                     "def audit(event,args):\n"
                     " if event in {'subprocess.Popen','os.system','os.posix_spawn','os.posix_spawnp'}:forbidden()\n"
                     "sys.addaudithook(audit)\nc.execute=forbidden\nc.route.source_readback=forbidden\n"
                     "raise SystemExit(c.main())\n")
            result=subprocess.run([sys.executable,'-c',program],cwd=root,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            value=json.loads((collector.OUT/'manifest.json').read_text())
            self.assertFalse(value['acceptance']);self.assertEqual(value['receipts'],[])

    def test_cleanup_arising_during_summary_prevents_attachment_export(self):
        with self.checkout():
            def uncertain(command,*args,**kwargs):
                os.environ['QRCATCHER_OWNED_CLEANUP_UNCONFIRMED']='true'
                return 0,json.dumps(summary()),dict(state='completed',cleanup_confirmed=True)
            with patch.object(collector,'execute',side_effect=uncertain) as execute:self.assertEqual(collector.main(),1)
            self.assertEqual(execute.call_count,1);self.assertFalse(collector.ATTACHMENTS.exists())

    def test_source_preserves_assertions_lifecycle_and_all_other_native_cases(self):
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        target=hosted.split('- (void)testLargestDynamicTypeFullTextAndActionsInBoundedPublicScrollPanes {',1)[1].split('- (void)testChineseTranslations',1)[0]
        for token in ['CGRectContainsRect(result.view.bounds, text.frame)', 'CGRectContainsRect(result.view.bounds, actions.frame)',
                      'CGRectContainsRect(text.bounds, beginning)', 'CGRectContainsRect(text.bounds, ending)',
                      'CGRectContainsRect(actions.bounds, rect)', 'body.bounds.size.height + 0.5', 'rect.size.height, 44',
                      'button.titleLabel.bounds.size.height+0.5', '[host addChildViewController:result]',
                      '[result didMoveToParentViewController:host]']:
            self.assertIn(token,target)
        self.assertEqual(target.count('[self attachGeometryBeforeContainment:'),4)
        self.assertEqual(target.count('CGSizeMake('),6)
        self.assertNotIn('makeKeyAndVisible',target)
        helper=hosted.split('- (void)attachGeometryBeforeContainment:',1)[1].split('- (void)testLargestDynamicType',1)[0]
        for forbidden in ['layoutIfNeeded','setNeedsLayout','scrollRectToVisible','body.text','payload.UTF8String','window.rootViewController','continueAfterFailure =']:
            self.assertNotIn(forbidden,helper)
        self.assertIn('XCTAttachmentLifetimeKeepAlways',helper)
        self.assertIn('data.length > 16 * 1024',helper)
        self.assertEqual(hosted.count('- (void)test'),7)

    def test_canonical_exporter_all_UI_import_acceptance_gates_unchanged(self):
        exporter=(ROOT/'scripts/export_ios_platform_screenshots.py').read_text()
        self.assertEqual(hashlib.sha256(exporter.encode()).hexdigest(),'c02c8c43e029993edfb8de6f2d2138ff0709550bedf9f50df90241598faf3535')

    def test_geometry_attachment_uses_documented_ObjectiveC_class_factory(self):
        # Apple documents +attachmentWithData:uniformTypeIdentifier: for ObjC.
        # Swift's convenience init(data:uniformTypeIdentifier:) is not an ObjC
        # instance selector. This lexical contract is not a native SDK build.
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        expected='XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.json"];'
        self.assertEqual(hosted.count(expected),1)
        self.assertNotIn('initWithData:',hosted)
        self.assertNotIn('[XCTAttachment alloc]',hosted)

    def test_geometry_attachment_wrong_selector_mutations_are_rejected(self):
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        expected='XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.json"];'
        def source_contract(source):
            return source.count(expected)==1 and 'initWithData:' not in source and '[XCTAttachment alloc]' not in source
        self.assertTrue(source_contract(hosted))
        for replacement in [
            'XCTAttachment *attachment = [[XCTAttachment alloc] initWithData:data uniformTypeIdentifier:@"public.json"];',
            'XCTAttachment *attachment = [XCTAttachment attachmentWithData:data];',
            'XCTAttachment *attachment = [XCTAttachment attachmentWithData:data uniformTypeIdentifier:@"public.data"];',
        ]:
            with self.subTest(replacement=replacement):
                self.assertFalse(source_contract(hosted.replace(expected,replacement)))

    def test_geometry_attachment_preserves_bounded_JSON_lifetime_name_and_ownership(self):
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        helper=hosted.split('- (void)attachGeometryBeforeContainment:',1)[1].split('- (void)testLargestDynamicType',1)[0]
        self.assertIn('NSData *data = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:&error];',helper)
        self.assertIn('if (!data || data.length > 16 * 1024)',helper)
        self.assertIn('attachment.name = [NSString stringWithFormat:@"phone-hosted-geometry-%@-%dx%d-%@", kind, (int)viewport.width, (int)viewport.height, stage];',helper)
        self.assertIn('attachment.lifetime = XCTAttachmentLifetimeKeepAlways;',helper)
        self.assertEqual(helper.count('[self addAttachment:attachment];'),1)

    def test_actual_C_comparison_types_are_int_not_boolean(self):
        # This proves the C expression type, not NSNumber/JSON behavior or an
        # Objective-C SDK build. Native round-trip assertions cover the latter.
        compiler=shutil.which('cc')
        self.assertIsNotNone(compiler)
        program='''#include <stddef.h>
void classify(void *window, void *superview, void *parent, void *host, void *presenter) {
_Static_assert(_Generic((window != NULL), int:1, default:0), "window comparison is int");
_Static_assert(_Generic((superview != NULL), int:1, default:0), "superview comparison is int");
_Static_assert(_Generic((parent == host), int:1, default:0), "parent comparison is int");
_Static_assert(_Generic((presenter != NULL), int:1, default:0), "presenter comparison is int");
_Static_assert(_Generic((_Bool)(window != NULL), _Bool:1, default:0), "explicit bool conversion differs");
}
'''
        result=subprocess.run([compiler,'-std=c11','-Wall','-Werror','-fsyntax-only','-x','c','-'],
                              input=program,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_all_eight_recorder_booleans_use_typed_numberWithBool(self):
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        expressions=['label.adjustsFontForContentSizeCategory','window != nil','view.superview != nil',
                     'view.hasAmbiguousLayout','view.hidden','scroll.scrollEnabled',
                     'result.parentViewController == host','result.presentingViewController != nil']
        self.assertEqual(hosted.count('[NSNumber numberWithBool:'),8)
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertEqual(hosted.count('[NSNumber numberWithBool:('+expression+')]'),1)
                self.assertNotIn('@('+expression+')',hosted)

    def test_native_serialized_boolean_type_assertion_stays_inside_existing_recorder(self):
        hosted=(ROOT/'QRCatcherTests/QRPhoneResultTests.m').read_text()
        helper=hosted.split('- (void)attachGeometryBeforeContainment:',1)[1].split('- (void)testLargestDynamicType',1)[0]
        self.assertIn('JSONObjectWithData:data options:0 error:&error',helper)
        self.assertIn('QRDiagnosticJSONBooleanTypesAreValid(roundTrip)',helper)
        self.assertIn('CFGetTypeID((__bridge CFTypeRef)value) != CFBooleanGetTypeID()',hosted)
        self.assertEqual(hosted.count('- (void)test'),7)
        self.assertLess(helper.index('QRDiagnosticJSONBooleanTypesAreValid(roundTrip)'),helper.index('[self addAttachment:attachment]'))

    def test_numeric_booleans_reject_with_exact_bounded_field_path_and_type(self):
        paths=[('parent_is_host',),('presented',),('host','window_attached'),('result','superview_present'),
               ('body','ambiguous_layout'),('title','hidden'),('text','scroll','scroll_enabled'),
               ('body_font','adjusts_for_category'),('buttons',0,'view','window_attached'),
               ('buttons',0,'font','adjusts_for_category')]
        for path in paths:
            for wrong in [0,1,'private payload must never be printed',[],None]:
                value=receipt(('text',320,568,'ending'));target=value
                for part in path[:-1]:target=target[part]
                target[path[-1]]=wrong
                expected='.'.join(str(part) for part in path).replace('buttons.0.','buttons[0].')
                with self.subTest(path=path,wrong_type=type(wrong).__name__),self.assertRaises(ValueError) as failed:
                    collector.receipt(json.dumps(value).encode())
                message=str(failed.exception)
                self.assertEqual(message,'Invalid observed boolean at '+expected+': '+type(wrong).__name__)
                self.assertNotIn('private payload',message);self.assertLess(len(message.encode()),128)

    def test_full_rejection_retains_type_path_but_never_copies_invalid_geometry(self):
        with self.checkout():
            def execute(command,*args,**kwargs):
                result=self.fake_execute(command,*args,**kwargs)
                if 'attachments' in command:
                    path=collector.ATTACHMENTS/'0.json';value=json.loads(path.read_text())
                    value['host']['window_attached']=0;path.write_text(json.dumps(value))
                return result
            with patch.object(collector,'execute',side_effect=execute):self.assertEqual(collector.main(),1)
            value=json.loads((collector.OUT/'manifest.json').read_text())
            self.assertEqual(value['error'],'Invalid observed boolean at host.window_attached: int')
            self.assertEqual(value['collection'],'REJECTED');self.assertFalse(value['acceptance'])
            self.assertEqual(value['receipts'],[]);self.assertEqual(list(collector.OUT.glob(collector.PREFIX+'*')),[])


if __name__=='__main__':unittest.main()
