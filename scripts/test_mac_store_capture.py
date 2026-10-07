"""Portable source, failure and retention contracts. Native capture remains unrun."""
import copy
import hashlib
import json
import os
import plistlib
import socket
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import mac_store_capture as m
import mac_store_contract as contract
import mac_store_product as product_contract
from test_mac_store_png import png
from test_mac_store_display import display_records
from test_mac_store_source_helpers import restore_store_app,restore_store_ui,STORE_CLASS,STORE_SETUP,STORE_METHODS

CHECKOUT=Path(__file__).resolve().parents[1]
SHA='a'*40;TREE='b'*40;TOKEN='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE'


class Clock:
    def __init__(self):self.value=100.
    def __call__(self):return self.value
    def advance(self,value):self.value+=value


def env():
    return {'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':m.BRANCH,
        'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+m.WORKFLOW+'@'+m.BRANCH,
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'capture','GITHUB_EVENT_NAME':'push',
        'GITHUB_SHA':SHA,'GITHUB_WORKFLOW_SHA':SHA,'GITHUB_RUN_ID':'123',
        'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer'}


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def exported(start,product,failed=False,scale=1):
    counts={'passedTests':0 if failed else 1,'failedTests':1 if failed else 0,'skippedTests':0,'expectedFailures':0}
    identity='QRCatcherMacUITests/'+m.CASE+'()'
    url='test://com.apple.xcode/QRCatcher/QRCatcherMacUITests/QRCatcherMacUITests/'+m.CASE
    summary={**counts,'totalTestCount':1,'result':'Failed' if failed else 'Passed','startTime':start+.1,'finishTime':start+1.8,
        'devicesAndConfigurations':[{**counts,'device':{'deviceId':'owned-Mac','platform':'macOS','architecture':'arm64','osVersion':'27.0'},
            'testPlanConfiguration':{'configurationName':'Test Scheme Action'}}],
        'testFailures':[{'testIdentifierString':identity,'testIdentifierURL':url}] if failed else []}
    items=[];files={}
    setup_raw,restore_raw=display_records(start,scale)
    display_digest=contract.digest(setup_raw)
    for index,(state,visible) in enumerate(contract.STATES.items()):
        raw=png(1280*scale,800*scale,color=(35+index,90,170));captured=start+.4+index*.6
        row={'v':1,'state':state,'token':TOKEN,'pid':456,'test':'-[QRCatcherMacUITests '+m.CASE+']',
            'started':start+.2,'captured':captured,'sequential':True,'args':contract.ARGS,'sandbox':False,
            'bundle':'100mango.QRCatcher',**product,'expectedPath':product['applicationPath'],
            'imageName':'Native Mac Store window '+state,'pngSHA256':contract.digest(raw),'pngBytes':len(raw),
            'width':1280*scale,'height':800*scale,'windowFrame':[80.,35.,1280.,800.],
            'backingScale':scale,'visibleFrameAX':[0,31,1440,809],'displaySetupSHA256':display_digest,
            **visible,'payloadSHA256':contract.digest(visible['payload'].encode('utf-8'))}
        for offset,(kind,ext,data) in enumerate([('window','png',raw),('proof','txt',encoded(row))]):
            uid='00000000-0000-4000-8000-'+str(index*2+offset+1).zfill(12);filename=uid+'.'+ext;files[filename]=data
            items.append({'configurationName':'Test Scheme Action','deviceId':'owned-Mac','deviceName':'My Mac',
                'exportedFileName':filename,'isAssociatedWithFailure':False,
                'suggestedHumanReadableName':'Native Mac Store '+kind+' '+state+'_0_'+uid+'.'+ext,'timestamp':captured+.01+offset*.01})
    for index,(suffix,raw) in enumerate([('setup',setup_raw),('restore',restore_raw)]):
        uid='00000000-0000-4000-8000-'+str(index+5).zfill(12);filename=uid+'.txt';files[filename]=raw
        items.append({'configurationName':'Test Scheme Action','deviceId':'owned-Mac','deviceName':'My Mac',
            'exportedFileName':filename,'isAssociatedWithFailure':False,
            'suggestedHumanReadableName':'Native Mac Store display '+suffix+'_0_'+uid+'.txt',
            'timestamp':start+(.19 if suffix=='setup' else 1.61)})
    files['manifest.json']=encoded([{'testIdentifier':identity,'testIdentifierURL':url,'attachments':items}])
    return summary,files


def release_projection(text):
    active=[True];out=[]
    for line in text.splitlines(keepends=True):
        directive=line.strip()
        if directive=='#if DEBUG':active.append(False)
        elif directive=='#else':active[-1]=active[-2] and not active[-1]
        elif directive=='#endif':active.pop()
        elif directive.startswith('#if '):raise ValueError('unknown conditional')
        elif active[-1]:out.append(line)
    if len(active)!=1:raise ValueError('unbalanced DEBUG')
    return ''.join(out)


class PortableTests(unittest.TestCase):
    def setUp(self):
        # Every OS/tool operation in these regressions is a local fake. An
        # accidental subprocess or network fallback must fail before it starts.
        for target in ('subprocess.Popen','os.system','socket.create_connection','socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('native/network operation forbidden in portable tests'))
            guard.start();self.addCleanup(guard.stop)


class SourceTests(PortableTests):
    def test_only_exact_debug_additions_and_new_test_are_removed(self):
        f=json.loads((CHECKOUT/'scripts/fixtures/mac-store-source-baseline.json').read_bytes())
        app=(CHECKOUT/'QRCatcherMac/QRCatcherMacApp.swift').read_text();ui=(CHECKOUT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        self.assertEqual(hashlib.sha256(restore_store_app(app).encode()).hexdigest(),f['original_app_inputs']['QRCatcherMac/QRCatcherMacApp.swift'])
        self.assertEqual(hashlib.sha256(restore_store_ui(ui).encode()).hexdigest(),f['ui_sha256'])
        self.assertEqual(release_projection(app),release_projection(restore_store_app(app)))
        self.assertNotIn('MacStoreCapture',release_projection(app))
    def test_thirty_eight_product_inputs_have_one_controlled_debug_difference(self):
        f=json.loads((CHECKOUT/'scripts/fixtures/mac-store-source-baseline.json').read_bytes());self.assertEqual(len(f['original_app_inputs']),38)
        self.assertEqual([k for k in f['original_app_inputs'] if f['original_app_inputs'][k]!=f['current_app_inputs'][k]],['QRCatcherMac/QRCatcherMacApp.swift'])
        for path,value in f['current_app_inputs'].items():self.assertEqual(hashlib.sha256((CHECKOUT/path).read_bytes()).hexdigest(),value,path)
    def test_existing_fixture_and_capture_support_inputs_remain_frozen(self):
        f=json.loads((CHECKOUT/'scripts/fixtures/mac-store-source-baseline.json').read_bytes())
        self.assertEqual(len(f['current_support_inputs']),16)
        for path,value in f['current_support_inputs'].items():
            self.assertEqual(hashlib.sha256((CHECKOUT/path).read_bytes()).hexdigest(),value,path)
    def test_constructor_change_cannot_be_hidden_by_store_source_restoration(self):
        f=json.loads((CHECKOUT/'scripts/fixtures/mac-store-source-baseline.json').read_bytes())
        app=(CHECKOUT/'QRCatcherMac/QRCatcherMacApp.swift').read_text()
        constructor='_workspace = StateObject(wrappedValue: MacWorkspace(history: MacHistory.applicationHistory()))'
        self.assertEqual(app.count(constructor),1)
        changed=app.replace(constructor,constructor+'; unexpectedConstructorSideEffect()',1)
        restored=restore_store_app(changed)
        self.assertIn('unexpectedConstructorSideEffect()',restored)
        self.assertNotEqual(hashlib.sha256(restored.encode()).hexdigest(),f['original_app_inputs']['QRCatcherMac/QRCatcherMacApp.swift'])
        self.assertNotEqual(release_projection(changed),release_projection(restore_store_app(app)))
    def test_source_restoration_rejects_duplicate_or_modified_approved_additions(self):
        app=(CHECKOUT/'QRCatcherMac/QRCatcherMacApp.swift').read_text()
        ui=(CHECKOUT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        for restore,text,part in [(restore_store_app,app,STORE_CLASS),(restore_store_ui,ui,STORE_METHODS)]:
            with self.subTest(restore=restore.__name__,kind='duplicate'),self.assertRaises(ValueError):restore(text+part)
            with self.subTest(restore=restore.__name__,kind='modified'),self.assertRaises(ValueError):restore(text.replace(part,part.replace('1280','1281',1),1))
    def test_resize_gate_is_debug_token_scoped_and_only_existing_window(self):
        self.assertIn('UUID(uuidString: token)?.uuidString == token',STORE_CLASS)
        self.assertIn('let prefix = "QRCatcherUITest-"',STORE_CLASS)
        self.assertIn('store.lastPathComponent == "coredata.sqlite"',STORE_CLASS)
        self.assertIn('FileManager.default.temporaryDirectory.resolvingSymlinksInPath()',STORE_CLASS)
        self.assertIn('guard !applied, let window else { return }',STORE_CLASS)
        self.assertLess(STORE_CLASS.index('applied = true'),STORE_CLASS.index('window.setFrame'))
        for bad in ['NSWindow(', 'NSApp','NSApplication','activate','makeKey','openWindow','Timer','DispatchQueue','UserDefaults']:
            self.assertNotIn(bad,STORE_CLASS)
        self.assertEqual(STORE_CLASS.count('window.setFrame'),1)
    def test_case_uses_real_product_actions_and_original_png(self):
        self.assertIn('try pasteStoreFixture("ascii", payload: url, historyCount: 1)',STORE_METHODS)
        self.assertIn('try pasteStoreFixture("unicode", payload: unicode, historyCount: 2)',STORE_METHODS)
        self.assertIn('app.buttons["mac.paste"].click()',STORE_METHODS)
        self.assertIn('app.buttons["mac.copy"].click()',STORE_METHODS)
        self.assertIn('NSPasteboard.general.string(forType: .string), payload',STORE_METHODS)
        self.assertLess(STORE_METHODS.index('try selectStoreHistory(url)'),STORE_METHODS.index('try selectStoreHistory(unicode)'))
        self.assertIn('labels.firstMatch.click()',STORE_METHODS)
        self.assertIn('let selected = rows.filter { $0.isSelected }',STORE_METHODS)
        self.assertIn('XCTAssertEqual(after.selectedPayload, before.selectedPayload)',STORE_METHODS)
        self.assertIn('let png = window.screenshot().pngRepresentation',STORE_METHODS)
        self.assertIn('XCTAssertEqual(app.sheets.count, 0)',STORE_METHODS);self.assertIn('XCTAssertEqual(app.dialogs.count, 0)',STORE_METHODS)
        for bad in ['app.launch()', 'NSWorkspace', 'NSWindow(', 'resize(', 'cropped(', 'draw(', 'performAccessibilityAudit', 'requestPublicMetadata']:
            self.assertNotIn(bad,STORE_METHODS+STORE_SETUP)
    def test_single_build_test_and_fixed_push_workflow(self):
        argv=m.test_command();self.assertEqual(argv[-1],'test-without-building');self.assertEqual([x for x in argv if x.startswith('-only-testing:')],['-only-testing:QRCatcherMacUITests/QRCatcherMacUITests/'+m.CASE])
        self.assertNotIn('-test-iterations',argv);self.assertIn('120',argv)
        text=(CHECKOUT/m.WORKFLOW).read_text();self.assertIn('timeout-minutes: 25',text);self.assertEqual(text.count('runs-on: xcode-27'),1)
        for bad in ['matrix:','workflow_dispatch','retry','continue-on-error','*.xcarchive','allowProvisioning']:self.assertNotIn(bad,text)
        self.assertIn('path: build/mac-store-proof/',text)
    def test_fixed_environment_excludes_retries_dispatch_and_other_branches(self):
        self.assertEqual(m.environment(env()),env())
        for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main')]:
            with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(env()|{key:value})
    def test_concrete_cohort_and_packet_caps(self):
        self.assertEqual(m.PHASE_END['finalization']+60,1310);self.assertEqual(1500-1310,190)
        self.assertEqual(contract.MAX_PACKET,14*1024*1024);self.assertEqual(m.MAX_REPORT,2*1024*1024)
    def test_display_change_is_in_runner_lifetime_before_original_launch(self):
        self.assertIn('try prepareStoreDisplay()',STORE_SETUP);self.assertIn('CGCompleteDisplayConfiguration(transaction, .forAppOnly)',STORE_METHODS)
        self.assertIn('allModes.prefix(128).map(storeModeRow)',STORE_METHODS);self.assertIn('no-supported-mode-fits-window',STORE_METHODS)
        self.assertEqual(STORE_METHODS.count('applyStoreDisplay('),3)
        for forbidden in ['.permanently','CGCaptureAllDisplays','CGDisplaySetDisplayMode','sudo','displayplacer','app.launch()']:
            self.assertNotIn(forbidden,STORE_METHODS)
        self.assertIn('visible.midX - frame.width / 2',STORE_CLASS)


class ProductTests(PortableTests):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.old=Path.cwd();os.chdir(self.root);self.addCleanup(os.chdir,self.old)
        self.app=self.root/'build/mac-tests/Build/Products/Debug/QRCatcherMac.app'
        (self.app/'Contents/MacOS').mkdir(parents=True)
        self.metadata={'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcherMac'}
        self.write_metadata()
        (self.app/'Contents/MacOS/QRCatcherMac').write_bytes(b'fake Mac launcher')
        (self.app/'Contents/MacOS/QRCatcherMac.debug.dylib').write_bytes(b'fake Mac logic')
    def write_metadata(self):
        (self.app/'Contents/Info.plist').write_bytes(plistlib.dumps(self.metadata))
    def test_fixed_mac_product_hashes_launcher_and_debug_logic(self):
        row=product_contract.product_identity()
        self.assertEqual(row,{'applicationPath':str(self.app),'executable':str(self.app/'Contents/MacOS/QRCatcherMac'),
            'executableSHA256':contract.digest(b'fake Mac launcher'),'logicSHA256':contract.digest(b'fake Mac logic')})
    def test_same_bundle_ios_and_tv_executables_are_rejected(self):
        for executable in ('QRCatcher','QRCatcherTV'):
            self.metadata['CFBundleExecutable']=executable;self.write_metadata()
            (self.app/'Contents/MacOS'/executable).write_bytes(b'same bundle, wrong platform executable')
            with self.subTest(executable=executable),self.assertRaisesRegex(ValueError,'wrong-product'):
                product_contract.product_identity()
    def test_missing_debug_logic_and_linked_products_are_rejected(self):
        logic=self.app/'Contents/MacOS/QRCatcherMac.debug.dylib';logic.unlink()
        with self.assertRaises(FileNotFoundError):product_contract.product_identity()
        foreign=self.root/'foreign.dylib';foreign.write_bytes(b'foreign');logic.symlink_to(foreign)
        with self.assertRaisesRegex(ValueError,'linked-product'):product_contract.product_identity()


class ProductAliasTests(ProductTests):
    """Run actual product-binding assertions with a macOS-like temp-name alias."""
    def setUp(self):
        outer=tempfile.TemporaryDirectory();self.addCleanup(outer.cleanup)
        parent=Path(outer.name).resolve();alias=parent/'temporary-root-alias'
        alias.symlink_to(parent,target_is_directory=True)
        factory=tempfile.TemporaryDirectory
        with patch.object(tempfile,'TemporaryDirectory',side_effect=lambda:factory(dir=alias)):
            super().setUp()
        self.assertNotEqual(Path(self.temp.name),Path(self.temp.name).resolve())


class ReceiptTests(PortableTests):
    def setUp(self):
        super().setUp()
        app=Path('/virtual/build/mac-tests/Build/Products/Debug/QRCatcherMac.app')
        self.product={'applicationPath':str(app),'executable':str(app/'Contents/MacOS/QRCatcherMac'),
            'executableSHA256':'c'*64,'logicSHA256':'d'*64}
    def validate(self,summary,files):
        def read(path,limit):
            self.assertLessEqual(len(files[path.name]),limit)
            return files[path.name]
        return contract.validate_capture(Path('/virtual'),encoded(summary),self.product,
            {'returncode':0,'started_epoch':100,'finished_epoch':102},read=read)
    def test_exact_ascii_unicode_history_receipts_and_utf8_digest(self):
        summary,files=exported(100,self.product);proof,images=self.validate(summary,files)
        self.assertEqual(set(images),set(m.IMAGE_NAMES))
        for state,expected in contract.STATES.items():
            row=proof['states'][state]['receipt']
            self.assertEqual({key:row[key] for key in expected},expected)
            self.assertEqual(row['payloadSHA256'],hashlib.sha256(row['payload'].encode('utf-8')).hexdigest())
    def test_bad_payload_digest_history_count_and_selection_are_rejected(self):
        changes=[('result','payload','https://example.com/another'),('history','payload','QRCatcher 你好 123'),
            ('result','payloadSHA256','f'*64),('history','payloadSHA256',hashlib.sha256(contract.STATES['history']['payload'].encode('utf-16')).hexdigest()),
            ('result','historyCount',True),('result','historyCount',0),('history','historyCount',1),('history','historyCount',2.0),
            ('result','selectedHistoryPayload',contract.STATES['result']['payload']),('history','selectedHistoryPayload',None),
            ('history','selectedHistoryPayload',contract.STATES['result']['payload'])]
        for state,key,value in changes:
            summary,files=exported(100,self.product)
            name='00000000-0000-4000-8000-00000000000'+('2' if state=='result' else '4')+'.txt'
            row=json.loads(files[name]);row[key]=value
            if key=='payload':row['payloadSHA256']=contract.digest(value.encode('utf-8'))
            files[name]=encoded(row)
            with self.subTest(state=state,key=key,value=value),self.assertRaisesRegex(ValueError,'capture-visible-state'):
                self.validate(summary,files)
    def test_missing_and_foreign_receipt_fields_are_rejected(self):
        for key in ('payload','payloadSHA256','historyCount','selectedHistoryPayload'):
            summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
            row=json.loads(files[name]);del row[key];files[name]=encoded(row)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'capture-receipt-fields'):self.validate(summary,files)
        summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
        row=json.loads(files[name]);row['paletteCount']=1;files[name]=encoded(row)
        with self.assertRaisesRegex(ValueError,'capture-receipt-fields'):self.validate(summary,files)
    def test_same_bundle_ios_tv_or_release_receipts_are_rejected(self):
        for folder,app,executable in [('Debug-iphoneos','QRCatcher','QRCatcher'),('Debug-appletvos','QRCatcherTV','QRCatcherTV'),('Release','QRCatcherMac','QRCatcherMac')]:
            summary,files=exported(100,self.product);name='00000000-0000-4000-8000-000000000002.txt'
            row=json.loads(files[name]);foreign='/virtual/build/mac-tests/Build/Products/'+folder+'/'+app+'.app'
            row.update(applicationPath=foreign,expectedPath=foreign,executable=foreign+'/Contents/MacOS/'+executable)
            files[name]=encoded(row)
            self.assertEqual(row['bundle'],'100mango.QRCatcher')
            with self.subTest(product=app,folder=folder),self.assertRaisesRegex(ValueError,'capture-product'):
                self.validate(summary,files)
    def test_wrong_project_identifier_url_is_rejected(self):
        summary,files=exported(100,self.product);groups=json.loads(files['manifest.json'])
        groups[0]['testIdentifierURL']=groups[0]['testIdentifierURL'].replace('/QRCatcher/','/QRCatcherMac/')
        files['manifest.json']=encoded(groups)
        with self.assertRaisesRegex(ValueError,'capture-foreign-exported-case'):self.validate(summary,files)


class Pipeline(PortableTests):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.old=Path.cwd();os.chdir(self.root)
        self.clock=Clock();self.calls=[];self.failed=False;self.zero=False;self.late=False;self.mutate=None;self.late_summary=False;self.cleanup_unknown=False;self.scale=1;self.build_error=None
        app=self.root/'build/mac-tests/Build/Products/Debug/QRCatcherMac.app'
        self.product={'applicationPath':str(app),'executable':str(app/'Contents/MacOS/QRCatcherMac'),'executableSHA256':'c'*64,'logicSHA256':'d'*64}
        source=m.source_identity
        self.source_patch=patch.object(m,'source_identity',side_effect=lambda e,run,root:source(e,run,CHECKOUT));self.source_patch.start()
        self.product_patch=patch.object(m,'product_identity',side_effect=lambda:dict(self.product));self.product_patch.start()
    def tearDown(self):
        self.product_patch.stop();self.source_patch.stop();os.chdir(self.old);self.temp.cleanup()
    def runner(self,argv,**kwargs):
        self.calls.append(argv);raw=b'';stderr=b'';code=0
        if argv[0]=='git':
            if argv[1:]==['rev-parse','HEAD']:raw=(SHA+'\n').encode()
            elif argv[1:]==['rev-parse',m.PARENT+'^{tree}']:raw=(m.PARENT_TREE+'\n').encode()
            elif argv[1:]==['rev-parse','HEAD^{tree}']:raw=(TREE+'\n').encode()
            elif argv[1]=='rev-list':raw=(SHA+' '+m.PARENT+'\n').encode()
            elif argv[1]=='diff':raw=('\n'.join(sorted(['M\t'+x for x in m.SUCCESSOR_PATHS]))+'\n').encode()
            else:self.assertEqual(argv[1],'status')
        elif argv==['sw_vers','-buildVersion']:raw=b'26A428\n'
        elif argv==['uname','-m']:raw=b'arm64\n'
        elif argv==['xcodebuild','-version']:raw=b'Xcode 27.0\nBuild version 27A266a\n'
        elif argv in ([sys.executable,'scripts/materialize_mac_icons.py'],[sys.executable,'scripts/materialize_qr_fixtures.py']):pass
        elif argv==m.base_command()+['build-for-testing']:
            if self.build_error=='stdout':raw=b'QRCatcherMac.swift:4:7: error: synthetic failed compilation\n'
            if self.build_error=='stderr':stderr=b'fatal error: synthetic failed compilation\n'
        elif argv==m.test_command():
            if self.cleanup_unknown:raise m.CaptureStopped('unconfirmed owned capture',False)
            self.summary,self.files=exported(self.clock(),self.product,self.failed,self.scale)
            if self.zero:self.summary.update(totalTestCount=0,passedTests=0,failedTests=0)
            if self.late_summary:self.summary['finishTime']+=300
            self.clock.advance(301 if self.late else 2);code=65 if self.failed else 0
        elif argv[:5]==['xcrun','xcresulttool','get','test-results','summary']:raw=encoded(self.summary)
        elif argv[:3]==['xcrun','xcresulttool','export']:
            folder=self.root/m.EXPORT;folder.mkdir(parents=True)
            if self.mutate:self.mutate(self.files)
            for name,data in self.files.items():(folder/name).write_bytes(data)
        else:self.assertIn('unittest',argv)
        self.clock.advance(.1);return subprocess.CompletedProcess(argv,code,raw,stderr)
    def execute(self):return m.execute(env=env(),root=self.root,clock=self.clock,wall=self.clock,runner=self.runner)
    def retained(self):
        result=self.execute();self.assertTrue(result['qualified'],result.get('failure'));marker=self.root/'output';marker.write_text('')
        value=m.retain_report(result,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        return value,marker
    def test_success_retains_two_native_and_two_rgb_files_pending_visual_review(self):
        value,marker=self.retained();self.assertEqual(len(value['commands']),23);self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES))
        self.assertFalse(value['store_qualified']);self.assertEqual(value['visual_acceptance'],'pending-human-review');self.assertEqual(marker.read_text(),'evidence_ready=true\n')
        self.assertEqual(self.calls.count(m.base_command()+['build-for-testing']),1);self.assertEqual(self.calls.count(m.test_command()),1)
    def test_fixed_preparation_and_original_clock_cover_all_twenty_three_commands(self):
        value,_=self.retained();commands=value['commands']
        self.assertEqual([row['command'] for row in commands[11:13]],
            [[sys.executable,'scripts/materialize_mac_icons.py'],[sys.executable,'scripts/materialize_qr_fixtures.py']])
        self.assertEqual(commands[13]['command'],m.base_command()+['build-for-testing'])
        self.assertEqual(commands[14]['command'],m.test_command())
        self.assertEqual([row['command'] for row in commands[:6]],[row['command'] for row in commands[17:]])
        began=value['clock']['started_monotonic'];self.assertEqual(began,100.)
        self.assertTrue(all(began<=row['start']<=row['end'] for row in commands))
        self.assertEqual(commands[14]['cleanup_reserve_seconds'],20)
        self.assertLess(commands[-1]['end'],value['clock']['report_ready_deadline'])
    def test_offline_replay_rejects_forged_command_clock_and_cleanup(self):
        self.retained();path=self.root/m.OUTPUT/'report.json';original=json.loads(path.read_bytes())
        changes=[(13,'end',100+m.PHASE_END['build']), (14,'start',99.),
            (14,'grant_seconds',0.), (14,'owned_host_observation','unconfirmed')]
        for index,key,new in changes:
            value=copy.deepcopy(original);value['commands'][index][key]=new;path.write_bytes(m.report_bytes(value))
            with self.subTest(index=index,key=key),self.assertRaises(m.Rejected):
                m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_native_hidpi_pixels_match_ax_points_times_real_scale(self):
        self.scale=2;value,_=self.retained()
        for state in ('result','history'):
            row=value['proof']['states'][state];self.assertEqual(row['receipt']['backingScale'],2)
            self.assertEqual([row['conversion']['width'],row['conversion']['height']],[2560,1600])
    def test_failed_explicit_restore_preserves_qualified_capture_components(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt';row=json.loads(files[name]);row['restored']=False;row['configurationResult']=1000;files[name]=encoded(row)
        self.mutate=mutate;value,_=self.retained();self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES));self.assertFalse(value['store_qualified'])
    def test_main_fails_unconfirmed_restore_while_retaining_qualified_capture(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt'
            row=json.loads(files[name]);row['restored']=False;row['configurationResult']=1000;files[name]=encoded(row)
        self.mutate=mutate;result=self.execute();self.assertTrue(result['qualified'],result.get('failure'))
        marker=self.root/'output';marker.write_text('');retain=m.retain_report
        with patch.object(m,'ROOT',self.root),patch.object(m,'execute',return_value=result), \
                patch.object(m,'retain_report',side_effect=lambda *a,**kw:retain(*a,root=self.root,clock=self.clock,**kw)), \
                patch.dict(os.environ,{'GITHUB_OUTPUT':str(marker)}),patch.object(sys,'argv',['mac_store_capture.py']),patch('builtins.print'):
            self.assertEqual(m.main(),1)
        retained=m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        self.assertTrue(retained['qualified']);self.assertEqual(retained['runner_cleanup'],'unconfirmed')
        self.assertFalse(retained['store_qualified']);self.assertEqual(set(retained['image_files']),set(m.IMAGE_NAMES))
        self.assertEqual(marker.read_text(),'evidence_ready=true\n')
    def test_asynchronous_restore_screen_keeps_images_and_offline_validation(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000006.txt';row=json.loads(files[name]);row['restored']=False
            row['after']['frame']=[0,0,1440,900];row['after']['cgBounds']=[0,0,1440,900]
            row['after']['visibleFrame']=[0,60,1440,809];files[name]=encoded(row)
        self.mutate=mutate;value,_=self.retained()
        self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES));self.assertEqual(len(value['commands']),23)
        restore=value['proof']['display']['restore'];self.assertEqual(restore['configurationResult'],0)
        self.assertEqual(restore['after']['mode']['width'],1024);self.assertEqual(restore['after']['frame'][2],1440)
        self.assertFalse(value['store_qualified'])
    def test_missing_restore_receipt_preserves_bound_capture_components(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['attachments']=[x for x in groups[0]['attachments'] if not x['suggestedHumanReadableName'].startswith('Native Mac Store display restore')];files['manifest.json']=encoded(groups)
        self.mutate=mutate;value,_=self.retained();self.assertTrue(value['qualified']);self.assertEqual(value['runner_cleanup'],'unconfirmed')
        self.assertEqual(set(value['image_files']),set(m.IMAGE_NAMES))
    def test_wrong_scale_or_offscreen_window_is_rejected(self):
        for key,value in [('backingScale',2),('windowFrame',[500,35,1280,800])]:
            summary,files=exported(100,self.product)
            name='00000000-0000-4000-8000-000000000002.txt';row=json.loads(files[name]);row[key]=value;files[name]=encoded(row)
            def read(path,limit):return files[path.name]
            with self.subTest(key=key),self.assertRaises(ValueError):contract.validate_capture(Path('/virtual'),encoded(summary),self.product,
                {'returncode':0,'started_epoch':100,'finished_epoch':102},read=read)
    def test_build_zero_exit_with_reported_error_prevents_test_launch(self):
        self.build_error='stdout';value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'build-reported-error')
        self.assertEqual(value['failure']['phase'],'build');self.assertEqual(len(self.calls),14)
        self.assertNotIn(m.test_command(),self.calls);self.assertEqual(value['image_files'],{})
    def test_build_zero_exit_with_stderr_fatal_error_prevents_test_launch(self):
        self.build_error='stderr';value=self.execute()
        self.assertFalse(value['qualified']);self.assertEqual(value['failure']['reason'],'build-reported-error')
        self.assertEqual(value['failure']['phase'],'build');self.assertEqual(len(self.calls),14)
        self.assertNotIn(m.test_command(),self.calls);self.assertEqual(value['image_files'],{})
    def test_original_failed_case_stays_failed_and_no_export(self):
        self.failed=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(value['test_outcome'],'failed');self.assertEqual(value['image_files'],{})
        self.assertEqual(len(self.calls),16);self.assertNotIn('export',self.calls[-1])
    def test_zero_case_fails_before_export(self):
        self.zero=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),16)
    def test_late_summary_fails_before_export(self):
        self.late_summary=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),16)
    def test_native_test_late_return_stops_before_evidence(self):
        self.late=True;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(len(self.calls),15)
    def test_uncertain_cleanup_never_starts_evidence_or_retries(self):
        self.cleanup_unknown=True;value=self.execute();self.assertFalse(value['qualified']);self.assertFalse(value['commands'][-1]['owned_cleanup_confirmed']);self.assertEqual(len(self.calls),15)
    def test_wrong_pid_on_second_capture_rejects_packet(self):
        def mutate(files):
            name='00000000-0000-4000-8000-000000000004.txt';r=json.loads(files[name]);r['pid']+=1;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('second-launch',value['failure']['reason'])
    def test_wrong_product_hash_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['logicSHA256']='f'*64;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('capture-product',value['failure']['reason'])
    def test_image_digest_mismatch_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['pngSHA256']='f'*64;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('pixel-binding',value['failure']['reason'])
    def test_transparency_keeps_bound_originals_but_fails_store_format(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);image=groups[0]['attachments'][0]['exportedFileName'];record=groups[0]['attachments'][1]['exportedFileName']
            files[image]=png(alpha=254);row=json.loads(files[record]);row['pngSHA256']=contract.digest(files[image]);row['pngBytes']=len(files[image]);files[record]=encoded(row)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertEqual(value['source_after'],value['source_before'])
        self.assertIn('native-result.png',value['image_files']);self.assertNotIn('store-result.png',value['image_files']);self.assertIn('result',value['proof']['formatFailures'])
        marker=self.root/'output';marker.write_text('');retained=m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertFalse(retained['qualified']);self.assertTrue((self.root/m.OUTPUT/'native-result.png').is_file())
    def test_exported_foreign_case_rejects_packet(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['testIdentifier']='Another/test()';files['manifest.json']=encoded(groups)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('foreign-exported',value['failure']['reason'])
    def test_unsafe_exported_name_rejects_packet(self):
        def mutate(files):
            groups=json.loads(files['manifest.json']);groups[0]['attachments'][0]['exportedFileName']='../other.png';files['manifest.json']=encoded(groups)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('file-name',value['failure']['reason'])
    def test_wrong_frame_rejects_packet(self):
        def mutate(files):
            name=next(x for x in files if x.endswith('.txt'));r=json.loads(files[name]);r['windowFrame'][2]=1024;files[name]=encoded(r)
        self.mutate=mutate;value=self.execute();self.assertFalse(value['qualified']);self.assertIn('window-size',value['failure']['reason'])
    def test_retained_image_tampering_is_rejected(self):
        self.retained();p=self.root/m.OUTPUT/'store-result.png';p.write_bytes(p.read_bytes()+b'x')
        with self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_forged_source_or_visual_acceptance_is_rejected(self):
        self.retained();p=self.root/m.OUTPUT/'report.json';original=json.loads(p.read_bytes())
        for key,value in [('store_qualified',True),('visual_acceptance','approved')]:
            changed=copy.deepcopy(original);changed[key]=value;p.write_bytes(m.report_bytes(changed))
            with self.subTest(key=key),self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha=SHA,tree=TREE,run_id=123,source_root=CHECKOUT)
        p.write_bytes(m.report_bytes(original))
        with self.assertRaises(m.Rejected):m.validate_packet(self.root/m.OUTPUT,sha='e'*40,tree=TREE,run_id=123,source_root=CHECKOUT)
    def test_upload_full_reserve_and_original_clock_are_required(self):
        value,_=self.retained();value['upload_observation']=m.admit_upload(value,clock=self.clock)
        self.assertTrue(m.finish_upload(value,'success',clock=self.clock)['upload_qualified']);self.assertFalse(m.finish_upload(value,'failure',clock=self.clock)['upload_qualified'])
        self.clock.advance(61);self.assertFalse(m.finish_upload(value,'success',clock=self.clock)['upload_qualified'])
    def test_upload_admission_cannot_reset_original_clock_or_shorten_reserves(self):
        value,_=self.retained();began=value['clock']['started_monotonic']
        for now in (began-1,began+m.PHASE_END['evidence']-60,began+m.PHASE_END['finalization']-80):
            with self.subTest(now=now),self.assertRaises(m.Rejected):m.admit_upload(value,clock=lambda:now)
        value['upload_observation']=m.admit_upload(value,clock=self.clock)
        value['upload_observation']['evidence_deadline']+=1
        receipt=m.finish_upload(value,'success',clock=self.clock)
        self.assertFalse(receipt['upload_qualified']);self.assertEqual(receipt['failure'],'upload-admission-identity-mismatch')
    def test_retention_lateness_never_emits_upload_marker(self):
        value=self.execute();self.assertTrue(value['qualified']);value['clock']['report_ready_deadline']=self.clock();marker=self.root/'output';marker.write_text('previous\n')
        with self.assertRaises(m.Rejected):m.retain_report(value,self.root/m.OUTPUT,marker,root=self.root,clock=self.clock)
        self.assertEqual(marker.read_text(),'previous\n')
    def test_oversized_report_does_not_publish_images_as_qualified(self):
        value=self.execute();value['commands']=['x'*(m.MAX_REPORT+1)];decoded=json.loads(m.report_bytes(value));self.assertFalse(decoded['qualified']);self.assertEqual(decoded['image_files'],{})


if __name__=='__main__':unittest.main()
