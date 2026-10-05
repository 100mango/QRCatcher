"""Executable portable source/schema adversaries, never native compiler evidence."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mac_public_metadata_schema', ROOT/'scripts/mac_public_metadata_schema.py')
schema = importlib.util.module_from_spec(spec); spec.loader.exec_module(schema)
TOKEN = '7FAAE2C9-89A0-4FFB-946D-3F01CB62C875'
REQUEST = 'EC0F402E-825D-4BFC-A186-318621835ED2'


class MacPublicMetadataTests(unittest.TestCase):
    def binding(self, case='testNativeWindowResizeKeepsFullActionTitles', checkpoint=None):
        checkpoint = checkpoint or schema.CASES[case][0]
        return dict(token=TOKEN, case=case, checkpoint=checkpoint, sequence=schema.CASES[case].index(checkpoint)+1,
                    request_id=REQUEST, request_time=100.0, now=102.0)

    def receipt(self, case='testNativeWindowResizeKeepsFullActionTitles', checkpoint=None, observed=False):
        bind = self.binding(case, checkpoint)
        window = dict(number=10, frame=[0, 100, 1000, 660], visible=True, key=True, main=True, sheetParent=-1, attachedSheet=-1)
        sheet = None
        if bind['checkpoint'] == 'mac-chinese-policy':
            sheet = dict(number=11, frame=[200, 300, 540, 250], visible=True, key=True, main=False, sheetParent=10, attachedSheet=-1)
            window['attachedSheet'] = 11; window['key'] = False
        rows = []
        for kind, identifier, pane, text, in_sheet in schema.target_specs(case, bind['checkpoint']):
            row = dict(kind=kind, identifier=identifier, pane=pane, expectedUTF16Length=schema.utf16(text), expectedSHA256=schema.digest(text),
                       state='UNKNOWN', reason='missing-target', matchCount=0, matchScope='visited-owned-public-nodes', attributedCall='not-run')
            if observed:
                root = sheet if in_sheet else window
                node = dict(role='AXStaticText', root='attached-sheet' if in_sheet else 'main-content', window=root['number'],
                            path=['mac.sheet.privacy' if in_sheet else 'mac.windowContent', pane, identifier or 'unidentified'],
                            frame=[root['frame'][0]+20, root['frame'][1]+20, 200, 20], enabled=False,
                            valueUTF16Length=schema.utf16(text), valueSHA256=schema.digest(text))
                attrs = {key: dict(state='UNKNOWN', type='absent') for key in schema.ATTRIBUTES}
                attrs['font'] = dict(state='OBSERVED', type='NSFont', name='.SFNS-Regular', pointSize=13.0, traits=0)
                attrs['foregroundColor'] = dict(state='OBSERVED', type='sRGB', components=[0.0, 0.0, 0.0, 1.0])
                row.update(state='OBSERVED', reason='public-attributed-string', matchCount=1, wrapper=node, queried=copy.deepcopy(node),
                           queryKind='exact-wrapper', attributedScope='complete-public-traversal', attributedCall='completed-matched', requestedRange=[0, schema.utf16(text)], returnedUTF16Length=schema.utf16(text),
                           returnedSHA256=schema.digest(text), runs=[dict(range=[0, schema.utf16(text)], attributes=attrs)])
            rows.append(row)
        return dict(schema=1, token=TOKEN, case=case, checkpoint=bind['checkpoint'], sequence=bind['sequence'], requestID=REQUEST,
                    uptime=101.0, auditQualified=False, contrastQualified=False, state='OBSERVED', issues=[], visitedNodes=20,
                    coordinateSpace='AppKit-screen-bottom-left', screens=1, screenFrame=[0,0,1024,768], active=True, keyWindow=11 if sheet else 10, mainWindow=10,
                    window=window, attachedSheet=sheet, orderedWindows=[11, 10] if sheet else [10], targets=rows)

    def validate(self, receipt, **binding):
        return schema.validate_native_receipt(json.dumps(receipt, allow_nan=True).encode(), **(binding or self.binding(receipt['case'], receipt['checkpoint'])))

    def reject(self, receipt, **binding):
        with self.assertRaises((ValueError, TypeError)):
            self.validate(receipt, **binding)

    def test_four_exact_checkpoints_observed_and_unknown(self):
        for case, checkpoints in schema.CASES.items():
            for checkpoint in checkpoints:
                for observed in [False, True]:
                    receipt=self.receipt(case, checkpoint, observed); self.assertEqual(self.validate(receipt), receipt)
                    self.assertIs(receipt['auditQualified'], False); self.assertIs(receipt['contrastQualified'], False)

    def test_missing_public_metadata_is_unknown_without_reference_font(self):
        receipt=self.receipt(observed=True)
        for row in receipt['targets']:
            row['runs'][0]['attributes']={key:dict(state='UNKNOWN',type='absent') for key in schema.ATTRIBUTES}
        self.validate(receipt)
        for bad in [dict(state='OBSERVED', type='reference', name='.body', pointSize=13.0), dict(state='OBSERVED', type='NSFont', name='.body', pointSize=13.0, traits=0, reference=True)]:
            value=copy.deepcopy(receipt);value['targets'][0]['runs'][0]['attributes']['font']=bad;self.reject(value)

    def test_wrong_token_case_checkpoint_sequence_stale_receipt(self):
        for field, bad in [('schema', True), ('token','00000000-0000-0000-0000-000000000000'), ('case','testImportCopyExportReopenAndSearch'),
                           ('checkpoint','mac-minimum-long-text-en'), ('sequence',True), ('sequence',2), ('requestID',TOKEN), ('uptime',99.0), ('uptime',103.0), ('uptime',True)]:
            receipt=self.receipt();receipt[field]=bad;self.reject(receipt, **self.binding())
        self.reject(self.receipt(), **dict(self.binding(), now=106.0))

    def test_request_gates_limits_duplicates_order_and_freshness(self):
        b=self.binding();r=dict(schema=1,token=TOKEN,case=b['case'],checkpoint=b['checkpoint'],sequence=1,requestID=REQUEST,uptime=101.0)
        args=dict(token=TOKEN,case=b['case'],checkpoint=b['checkpoint'],sequence=1,request_id=REQUEST,started=100.0,now=102.0)
        self.assertEqual(schema.validate_request(json.dumps(r).encode(),**args),r)
        for kw in [dict(requests=6),dict(requests=1),dict(consumed_ids=[REQUEST]),dict(consumed_checkpoints=[b['checkpoint']]),dict(now=107.0),dict(started=102.0)]:
            with self.assertRaises(ValueError):schema.validate_request(json.dumps(r).encode(),**dict(args,**kw))
        for field,bad in [('schema',True),('sequence',True),('uptime',True),('token',TOKEN.lower()),('value','arbitrary history')]:
            bad_r=copy.deepcopy(r);bad_r[field]=bad
            with self.assertRaises(ValueError):schema.validate_request(json.dumps(bad_r).encode(),**args)

    def test_duplicate_wrong_missing_targets_never_observed(self):
        for change in ['duplicate','missing','wrong-kind','wrong-pane','wrong-hash','wrong-length','match-count']:
            receipt=self.receipt(observed=True)
            if change=='duplicate':receipt['targets'].append(copy.deepcopy(receipt['targets'][0]))
            elif change=='missing':receipt['targets'].pop()
            elif change=='wrong-kind':receipt['targets'][0]['kind']='history-row'
            elif change=='wrong-pane':receipt['targets'][0]['pane']='mac.pane.history'
            elif change=='wrong-hash':receipt['targets'][0]['queried']['valueSHA256']='a'*64
            elif change=='wrong-length':receipt['targets'][0]['queried']['valueUTF16Length']=4097
            else:receipt['targets'][0]['matchCount']=2
            self.reject(receipt)

    def test_unsupported_cycle_overflow_requires_unknown(self):
        for issue in ['unsupported-public-node','cycle','depth-limit','node-limit','outside-root-or-unknown-owner']:
            receipt=self.receipt();receipt['state']='UNKNOWN';receipt['issues']=[issue];self.validate(receipt)
            receipt['state']='OBSERVED';self.reject(receipt)
            receipt=self.receipt(observed=True);receipt['state']='UNKNOWN';receipt['issues']=[issue];self.reject(receipt)
        receipt=self.receipt();receipt['visitedNodes']=257;self.reject(receipt)
        receipt=self.receipt();receipt['orderedWindows']=[10]*9;self.reject(receipt)

    def test_outside_root_pane_frame_and_wrong_child_rejected(self):
        for field, bad in [('root','outside-main-window'),('window',99),('path',['mac.windowContent','mac.pane.history']),('frame',[-50,50,200,20]),('frame',[20,120,float('nan'),20]),('enabled',0)]:
            receipt=self.receipt(observed=True);receipt['targets'][0]['queried'][field]=bad;self.reject(receipt)
        receipt=self.receipt(observed=True);row=receipt['targets'][0];row['queryKind']='direct-rendered-static-text';row['wrapper']['valueUTF16Length']=-1;row['wrapper']['valueSHA256']='unknown';row['queried']['path'].append('unidentified');self.validate(receipt)
        row['queried']['path'].append('unidentified');self.reject(receipt)

    def test_wrong_sheet_modal_state_remains_unknown(self):
        for checkpoint in ['mac-chinese-reopened','mac-chinese-policy']:
            receipt=self.receipt('testChineseCriticalFlow',checkpoint,True)
            if checkpoint.endswith('policy'):receipt['attachedSheet']['sheetParent']=99
            else:receipt['attachedSheet']=dict(number=11,frame=[0,0,100,100],visible=True,key=True,main=False,sheetParent=10,attachedSheet=-1)
            self.reject(receipt)

    def test_attributed_ranges_runs_and_metadata_types_fail_closed(self):
        for change in ['range','returned-hash','returned-length','too-many-runs','nonfinite-font','wrong-font','oversize-name','wrong-color','out-of-gamut','missing-key','extra-key']:
            receipt=self.receipt(observed=True);row=receipt['targets'][0];attrs=row['runs'][0]['attributes']
            if change=='range':row['requestedRange']=[0,4097]
            elif change=='returned-hash':row['returnedSHA256']='b'*64
            elif change=='returned-length':row['returnedUTF16Length']+=1
            elif change=='too-many-runs':row['runs']*=17
            elif change=='nonfinite-font':attrs['font']['pointSize']=float('inf')
            elif change=='wrong-font':attrs['font']['pointSize']=True
            elif change=='oversize-name':attrs['font']['name']='n'*129
            elif change=='wrong-color':attrs['foregroundColor']['type']='preferred-theme'
            elif change=='out-of-gamut':attrs['foregroundColor']['components'][0]=1.1
            elif change=='missing-key':attrs.pop('backgroundColor')
            else:attrs['foregroundColor']['inferred']=True
            self.reject(receipt)

    def test_typed_documented_font_dictionary_is_bounded(self):
        receipt=self.receipt(observed=True);attr=receipt['targets'][0]['runs'][0]['attributes']
        attr['accessibilityFont']=dict(state='OBSERVED',type='AXFontDictionary',name='Helvetica',pointSize=13.0,family='Helvetica',visibleName='Helvetica Regular');self.validate(receipt)
        attr['accessibilityFont']['pointSize']=False;self.reject(receipt)

    def test_raw_payload_text_extra_keys_oversize_duplicate_json_rejected(self):
        for where in ['top','target','node','attribute']:
            receipt=self.receipt(observed=True)
            target={'top':receipt,'target':receipt['targets'][0],'node':receipt['targets'][0]['queried'],'attribute':receipt['targets'][0]['runs'][0]['attributes']['font']}[where]
            target['text']='private arbitrary history';self.reject(receipt)
        b=self.binding()
        for data in [b' '*32769,b'{"schema":1,"schema":1}',b'\xff',b'{"value":NaN}']:
            with self.assertRaises(ValueError):schema.validate_native_receipt(data,**b)

    def test_audit_and_contrast_never_qualified_even_valid_disabled_nodes(self):
        self.validate(self.receipt(observed=True))
        for field in ['active']:
            for bad in [1, 0, None, 'true']:
                receipt=self.receipt(observed=True);receipt[field]=bad;self.reject(receipt)
        for field in ['visible', 'key', 'main']:
            receipt=self.receipt(observed=True);receipt['window'][field]=1;self.reject(receipt)
        for field in ['auditQualified','contrastQualified']:
            for bad in [True,0,None,'false']:
                receipt=self.receipt(observed=True);receipt[field]=bad;self.reject(receipt)

    def test_selected_case_bodies_and_original_audit_body_are_exact(self):
        source=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text()
        hashes={'testChineseCriticalFlow':'8e2e68f1a8220389ab98332b7f4e3d220cbedbfe0bfab80155676dede9dcbf19',
                'testNativeWindowResizeKeepsFullActionTitles':'62fc15f351465b4cccf9ac58ad7242a30af1321ff2d3e62c0910e8c5f1bcba7d'}
        for name,digest in hashes.items():
            signature='    func '+name+'() throws {'
            case=signature+source.split(signature,1)[1].split('\n    func test',1)[0]
            self.assertEqual(hashlib.sha256(case.encode()).hexdigest(),digest)
        self.assertEqual(source.count('\n    func test'),7)
        self.assertEqual(source.count('collectPublicMetadataIfSelected(name)'),1)
        audit='    private func screenshot(_ name: String) throws {'+source.split('    private func screenshot(_ name: String) throws {',1)[1].split('\n    func test',1)[0]
        audit=audit.replace('        #if DEBUG\n        collectPublicMetadataIfSelected(name)\n        #endif\n','')
        self.assertEqual(hashlib.sha256(audit.encode()).hexdigest(),'3cf10415bcd63468208228a0f3ce020febc5820df2a71a919ac83a0cd9559b70')

    def test_source_guards_and_executable_mutations(self):
        app=(ROOT/'QRCatcherMac/QRCatcherMacApp.swift').read_text();ui=(ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text();release=(ROOT/'scripts/verify_mac_release.py').read_text()
        self.assertTrue(schema.validate_observer_source(app,ui,release))
        mutations=['attempts < 6','requests < 6','bytes.count <= 1024','sequence == requests + 1','!acceptedRequests.contains(requestID)',
                   '!acceptedCheckpoints.contains(checkpoint)','systemUptime - requestTime <= 5','data.count <= 32768','depth <= 16',
                   'visits < 256','as? NSAccessibilityProtocol','view.window === root','ownWindow === root','active.contains(identity)',
                   'matching.count == 1','wrapper.object.accessibilityValue() == nil','rendered.count == 1','value.utf16.count <= 4096','runs.count < 16','targets.prefix(8)',
                   'accessibilityAttributedString(for: range)','queried.root.frame.contains','"auditQualified": false, "contrastQualified": false',
                   'event.keyCode == 25, !event.isARepeat','NSEvent.removeMonitor(monitor)','board.changeCount == change','guard issues.isEmpty','typedPublicMetadataBooleans(encoded)']
        for token in mutations:
            with self.subTest(removed=token),self.assertRaises(ValueError):schema.validate_observer_source(app.replace(token,'REMOVED_GUARD'),ui,release)
        for forbidden in ['as? CGColor','as! CGColor','CFGetTypeID(value','AXUIElement','addGlobalMonitor','NSPasteboard.general','setAccessibility','preferredFont']:
            with self.subTest(added=forbidden),self.assertRaises(ValueError):schema.validate_observer_source(app+'\n'+forbidden,ui,release)

    def test_debug_elision_excludes_all_product_observer_markers(self):
        source=(ROOT/'QRCatcherMac/QRCatcherMacApp.swift').read_text()
        kept=[]; excluded=[]
        for line in source.splitlines(True):
            directive=line.strip()
            if directive=='#if DEBUG':excluded.append(True);continue
            if directive=='#else' and excluded:excluded[-1]=not excluded[-1];continue
            if directive=='#endif' and excluded:excluded.pop();continue
            if not any(excluded):kept.append(line)
        self.assertEqual(excluded,[])
        release=''.join(kept)
        for marker in ['MacAuditPublicMetadataObserver','QRCATCHER_MAC_PUBLIC_METADATA_','QRCatcher.MacPublicMetadata.','org.qrcatcher.mac-public-metadata.','MAC_PUBLIC_METADATA_','addLocalMonitorForEvents','accessibilityAttributedString(for:']:
            self.assertNotIn(marker,release)
        self.assertIn('marker.setAccessibilityElement(false)',release)

    def test_release_absence_gate_executes_in_normal_and_optimized_python(self):
        source=ast.parse((ROOT/'scripts/verify_mac_release.py').read_text())
        loops=[n for n in source.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='marker']
        self.assertEqual(len(loops),1)
        code=compile(ast.Module(body=loops,type_ignores=[]),'<actual-release-absence-loop>','exec')
        exec(code,dict(strings='Normal Release product strings'))
        for marker in ['QRCATCHER_MAC_PUBLIC_METADATA_', 'QRCatcher.MacPublicMetadata.', 'org.qrcatcher.mac-public-metadata.', 'MacAuditPublicMetadataObserver', 'MAC_PUBLIC_METADATA_']:
            with self.assertRaises(ValueError):exec(code,dict(strings='prefix '+marker+' suffix'))

    def paired_receipt(self, case='testNativeWindowResizeKeepsFullActionTitles', checkpoint=None):
        native=self.receipt(case,checkpoint,observed=True); b=self.binding(case,checkpoint)
        def ui(frame):return [frame[0],768-frame[1]-frame[3],frame[2],frame[3]]
        paired=dict(windows=1,mainWindowMatches=1,windowFrame=ui(native['window']['frame']),sheets=1 if native['attachedSheet'] else 0,dialogs=0,foreground=True,
                    screenFrame=[0,0,1024,768],screens=1,coordinateSpace='XCTest-screen-top-left',targets=[])
        for target in native['targets']:
            paired['targets'].append(dict(kind=target['kind'],matches=1,frame=ui(target['wrapper']['frame']),
                                          valueUTF16Length=target['expectedUTF16Length'],valueSHA256=target['expectedSHA256']))
        return dict(schema=1,token=TOKEN,case=case,checkpoint=b['checkpoint'],sequence=b['sequence'],requestID=REQUEST,auditQualified=False,
                    contrastQualified=False,sameState='OBSERVED',reason='bounded-public-pair',native=native,paired=paired,generalChangeCountUnchanged=True)

    def test_four_same_state_pairs_use_actual_full_screen_conversion(self):
        for case,checkpoints in schema.CASES.items():
            for checkpoint in checkpoints:
                value=self.paired_receipt(case,checkpoint)
                self.assertEqual(schema.validate_paired_receipt(json.dumps(value).encode(),**self.binding(case,checkpoint)),value)
                self.assertFalse(value['auditQualified']);self.assertFalse(value['contrastQualified'])

    def test_changed_pair_geometry_state_clipboard_or_numeric_boolean_is_unqualified(self):
        for change in ['raw-y','visible-frame','second-screen','different-screen','clipboard-changed','numeric-clipboard','not-foreground','wrong-sheet','wrong-payload','moved-text','numeric-enabled','wrong-coordinate-space','extra-window','wrong-key-window','wrong-main-window']:
            value=self.paired_receipt()
            if change=='raw-y':value['paired']['windowFrame']=value['native']['window']['frame']
            elif change=='visible-frame':value['paired']['screenFrame']=[0,31,1024,674]
            elif change=='second-screen':value['paired']['screens']=2
            elif change=='different-screen':value['native']['screenFrame']=[0,0,1024,800]
            elif change=='clipboard-changed':value['generalChangeCountUnchanged']=False
            elif change=='numeric-clipboard':value['generalChangeCountUnchanged']=1
            elif change=='not-foreground':value['paired']['foreground']=False
            elif change=='wrong-sheet':value['paired']['sheets']=1
            elif change=='wrong-payload':value['paired']['targets'][0]['valueSHA256']='a'*64
            elif change=='moved-text':value['paired']['targets'][0]['frame'][0]+=3
            elif change=='numeric-enabled':value['native']['targets'][0]['queried']['enabled']=0
            elif change=='extra-window':value['paired']['windows']=2
            elif change=='wrong-key-window':value['native']['keyWindow']=99
            elif change=='wrong-main-window':value['native']['mainWindow']=99
            else:value['paired']['coordinateSpace']='AppKit-screen-bottom-left'
            with self.subTest(change=change), self.assertRaises(ValueError):schema.validate_paired_receipt(json.dumps(value).encode(),**self.binding())

    def partial_receipt(self, call='completed-matched', case='testNativeWindowResizeKeepsFullActionTitles', checkpoint=None):
        receipt = self.receipt(case, checkpoint)
        receipt.update(state='UNKNOWN', issues=['unsupported-public-node'])
        row = copy.deepcopy(self.receipt(case, checkpoint, observed=True)['targets'][0])
        row.update(state='UNKNOWN', reason='partial-public-attributed-string', attributedScope='partial-owned-exact-wrapper', attributedCall=call)
        if call in ['completed-nil', 'completed-mismatched']:
            for key in ['returnedUTF16Length', 'returnedSHA256', 'runs']:
                row.pop(key)
            row['reason'] = 'unsupported-or-mismatched-attributed-string'
        receipt['targets'][0] = row
        return receipt

    def test_partial_exact_wrapper_four_checkpoints_keeps_global_and_target_unknown(self):
        for case, checkpoints in schema.CASES.items():
            for checkpoint in checkpoints:
                value = self.partial_receipt(case=case, checkpoint=checkpoint)
                self.assertEqual(self.validate(value), value)
                self.assertEqual(value['state'], 'UNKNOWN')
                self.assertEqual(value['targets'][0]['state'], 'UNKNOWN')
                self.assertEqual(value['targets'][0]['matchScope'], 'visited-owned-public-nodes')
                self.assertFalse(value['auditQualified']); self.assertFalse(value['contrastQualified'])
                self.assertTrue(all(row['attributedCall'] == 'not-run' for row in value['targets'][1:]))

    def test_partial_completed_nil_mismatched_and_matched_returns_are_distinct(self):
        for call in ['completed-nil', 'completed-mismatched', 'completed-matched']:
            value = self.partial_receipt(call)
            self.validate(value)
            self.assertEqual(value['targets'][0]['attributedCall'], call)
            for field, bad in [('attributedCall', 'started'), ('attributedCall', 'not-run'), ('attributedCall', True), ('attributedScope', 'inferred-global')]:
                mutated = copy.deepcopy(value); mutated['targets'][0][field] = bad; self.reject(mutated)
            for field in ['attributedCall', 'matchScope', 'attributedScope', 'requestedRange']:
                mutated = copy.deepcopy(value); mutated['targets'][0].pop(field); self.reject(mutated)
        for call in ['completed-nil', 'completed-mismatched']:
            for field, bad in [('returnedUTF16Length', 40), ('returnedSHA256', 'a'*64), ('runs', [])]:
                value = self.partial_receipt(call); value['targets'][0][field] = bad; self.reject(value)

    def test_partial_unsafe_issue_or_direct_child_never_calls(self):
        for issue in schema.ISSUES - {'unsupported-public-node'}:
            for issues in [[issue], ['unsupported-public-node', issue]]:
                for call in ['completed-nil', 'completed-matched']:
                    value = self.partial_receipt(call); value['issues'] = issues; self.reject(value)
        value = self.partial_receipt(); row = value['targets'][0]
        row['queryKind'] = 'direct-rendered-static-text'
        row['queried']['path'].append('unidentified'); row['wrapper']['valueUTF16Length'] = -1; row['wrapper']['valueSHA256'] = 'unknown'
        self.reject(value)
        value = self.partial_receipt(); value['issues'] = []; value['state'] = 'OBSERVED'; self.reject(value)

    def test_partial_duplicate_missing_outside_root_wrong_value_frame_range_rejected(self):
        for field, bad in [('matchCount', 0), ('matchCount', 2), ('matchScope', 'complete-global-uniqueness'), ('requestedRange', [0, 4097]), ('requestedRange', [False, 40])]:
            value = self.partial_receipt(); value['targets'][0][field] = bad; self.reject(value)
        for field, bad in [('root', 'unowned'), ('window', 99), ('path', ['mac.windowContent', 'mac.pane.history']),
                           ('frame', [-100, 100, 200, 20]), ('frame', [20, 120, 0, 20]), ('frame', [20, 120, float('nan'), 20]),
                           ('valueSHA256', 'b'*64), ('valueUTF16Length', 4097)]:
            value = self.partial_receipt()
            for node in ['wrapper', 'queried']:
                value['targets'][0][node][field] = copy.deepcopy(bad)
            self.reject(value)

    def test_partial_supported_attributes_are_scoped_missing_types_never_inferred(self):
        value = self.partial_receipt(); attrs = value['targets'][0]['runs'][0]['attributes']
        attrs['accessibilityFont'] = dict(state='OBSERVED', type='AXFontDictionary', name='Helvetica', pointSize=13.0)
        attrs['backgroundColor'] = dict(state='UNKNOWN', type='unsupported')
        self.validate(value)
        for key in schema.ATTRIBUTES:
            attrs[key] = dict(state='UNKNOWN', type='absent')
        self.validate(value)
        attrs['backgroundColor'] = dict(state='OBSERVED', type='inferred-sRGB', components=[1,1,1,1]); self.reject(value)

    def test_partial_matched_return_bad_runs_remain_unknown_without_run_results(self):
        for reason in ['invalid-attribute-range', 'run-limit']:
            value = self.partial_receipt(); row = value['targets'][0]; row.pop('runs'); row['reason'] = reason
            self.validate(value)
            row['runs'] = []; self.reject(value)
        for change in ['too-many-runs', 'range-overflow', 'gap', 'wrong-hash', 'wrong-type']:
            value = self.partial_receipt(); row = value['targets'][0]
            if change == 'too-many-runs': row['runs'] *= 17
            elif change == 'range-overflow': row['runs'][0]['range'][1] += 1
            elif change == 'gap': row['runs'][0]['range'][0] = 1
            elif change == 'wrong-hash': row['returnedSHA256'] = 'a'*64
            else: row['runs'][0]['attributes']['font']['pointSize'] = False
            self.reject(value)

    def test_partial_cannot_qualify_global_target_pair_audit_or_contrast(self):
        for level in ['global', 'target', 'audit', 'contrast']:
            value = self.partial_receipt()
            if level == 'global': value['state'] = 'OBSERVED'
            elif level == 'target': value['targets'][0]['state'] = 'OBSERVED'
            elif level == 'audit': value['auditQualified'] = True
            else: value['contrastQualified'] = True
            self.reject(value)
        value = self.paired_receipt(); value['native'] = self.partial_receipt(); value.update(sameState='UNKNOWN', reason='state-or-geometry-mismatch')
        self.assertEqual(schema.validate_paired_receipt(json.dumps(value).encode(), **self.binding()), value)
        value.update(sameState='OBSERVED', reason='bounded-public-pair')
        with self.assertRaises(ValueError): schema.validate_paired_receipt(json.dumps(value).encode(), **self.binding())

    def test_partial_stale_oversize_and_arbitrary_content_fail_closed(self):
        value = self.partial_receipt(); value['uptime'] = 90; self.reject(value)
        for field in ['text', 'value', 'backgroundSource']:
            value = self.partial_receipt(); value['targets'][0][field] = 'arbitrary private content'; self.reject(value)
        value = self.partial_receipt(); value['targets'][0]['runs'][0]['attributes']['font']['name'] = 'n'*129; self.reject(value)
        with self.assertRaises(ValueError): schema.validate_native_receipt(b' '*32769, **self.binding())

    def test_partial_source_guard_order_and_completion_mutations_fail_closed(self):
        app = (ROOT/'QRCatcherMac/QRCatcherMacApp.swift').read_text(); ui = (ROOT/'QRCatcherMacUITests/QRCatcherMacUITests.swift').read_text(); release = (ROOT/'scripts/verify_mac_release.py').read_text()
        for token in ['issues == Set(["unsupported-public-node"]) && queryKind == "exact-wrapper"', '"matchScope": "visited-owned-public-nodes"',
                      'result["attributedCall"] = "completed-nil"', 'result["attributedCall"] = "completed-mismatched"',
                      'result["attributedCall"] = "completed-matched"', 'partial ? "UNKNOWN" : "OBSERVED"']:
            with self.subTest(token=token), self.assertRaises(ValueError): schema.validate_observer_source(app.replace(token, 'REMOVED_GUARD'), ui, release)
        old = 'let partial = issues == Set(["unsupported-public-node"]) && queryKind == "exact-wrapper"'
        with self.assertRaises(ValueError): schema.validate_observer_source(app.replace(old, old+' || true'), ui, release)
        call = 'let returned = queried.object.accessibilityAttributedString(for: range)'
        with self.assertRaises(ValueError): schema.validate_observer_source(app.replace(call, '').replace('guard let value = stringValue(queried.object)', call+'\n            guard let value = stringValue(queried.object)'), ui, release)
        for token in ['issues == ["unsupported-public-node"]', 'value["state"] as? String == "UNKNOWN", target["state"] as? String == "UNKNOWN"']:
            with self.assertRaises(ValueError): schema.validate_observer_source(app, ui.replace(token, 'REMOVED_GUARD'), release)

    def test_unknown_paired_response_can_never_be_a_pass(self):
        b=self.binding();value=dict(schema=1,token=TOKEN,case=b['case'],checkpoint=b['checkpoint'],sequence=1,requestID=REQUEST,auditQualified=False,
                                   contrastQualified=False,sameState='UNKNOWN',reason='missing-or-invalid-receipt')
        self.assertEqual(schema.validate_paired_receipt(json.dumps(value).encode(),**b),value)
        for key,bad in [('sameState','OBSERVED'),('auditQualified',True),('reason','bounded-public-pair'),('text','arbitrary history')]:
            bad_value=copy.deepcopy(value);bad_value[key]=bad
            with self.assertRaises(ValueError):schema.validate_paired_receipt(json.dumps(bad_value).encode(),**b)


if __name__=='__main__':unittest.main()
