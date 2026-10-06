#!/usr/bin/env python3
"""Exercise actual shell routing with isolated commands, never app runtime.
Runs the host Bash, including macOS Bash3.2 in CI; only disposable test files.
"""
from pathlib import Path
import ast,json,os,plistlib,shutil,subprocess,tempfile
def launcher_fixture_environment(environment, folder):
    # These scenarios own the default launcher identity. The dedicated staged
    # route has a separate complete source-bound fixture in its route suite.
    fixture = {**environment, 'GITHUB_WORKSPACE': str(folder),
               'GITHUB_ENV': str(folder/'fixture-github-env'),
               'GITHUB_REF': 'refs/heads/codex/apple-platforms'}
    for key in ('IOS_FIRST_RELEASE_CANDIDATE_ONLY',
                'QRCATCHER_IOS_SUPPLEMENT_ONLY',
                'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED', 'EVIDENCE_SCOPE'):
        fixture.pop(key, None)
    return fixture

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='qrcatcher-launcher-routing-') as directory:
    # macOS exposes temporary roots through /var -> /private/var. Exercise a
    # real owned alias on every host, then pass the same canonical root to both
    # the fixture workspace and the unchanged production ownership guard.
    temporary=Path(directory).resolve()
    workspace=temporary/'workspace';workspace.mkdir()
    alias=temporary/'workspace-alias';alias.symlink_to(workspace,target_is_directory=True)
    folder=alias.resolve();binary=folder/'bin';binary.mkdir();(folder/'scripts').mkdir()
    fixture_env=launcher_fixture_environment(os.environ,folder)
    for name in ['run_ios_platform_ui.sh','run_bounded.py','watch_process.py','owned_process_group.py','owned_process_barrier.py','atomic_json.py','stage_owned_import_fixture.py', 'fixture_query_guard.py','ios_import_continuation.py']:
        shutil.copyfile(root/'scripts'/name,folder/'scripts'/name)
    rejected=subprocess.run(['python3','scripts/owned_process_barrier.py','--check'],cwd=folder,
        env={**fixture_env,'GITHUB_WORKSPACE':str(alias),'QRCATCHER_OWNED_PROCESS_BARRIER':str(alias/'build/owned-process-cleanup.json')},capture_output=True,text=True,timeout=5)
    assert rejected.returncode==126,(rejected.returncode,rejected.stdout,rejected.stderr)
    print('OWNED_WORKSPACE_ALIAS_REJECTION_PASS raw alias rejected; canonical routing follows',flush=True)
    app=folder/'synthetic-app';app.mkdir();data=folder/'synthetic-data';data.mkdir()
    (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
    (folder/'Tests/Fixtures').mkdir(parents=True)
    (folder/'Tests/Fixtures/unicode.png').write_bytes(b'Isolated routing-test bytes, not a decoded app fixture')
    stub='''#!/usr/bin/env python3
import sys,json,os
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
p=Path(os.environ['OBSERVED_COMMAND']);rows=json.loads(p.read_text()) if p.exists() else [];rows.append({'tool':name,'args':args});p.write_text(json.dumps(rows))
if name=='xcodebuild':
 if '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' in args:status='FILE_STATUS'
 elif '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPhotosImportAndReopen' in args or '-only-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' in args:status='PHOTO_STATUS'
 else:status='TEST_STATUS'
 if status=='FILE_STATUS' and os.environ.get('BARRIER_AFTER_FILES')=='true':
  marker=Path(os.environ['QRCATCHER_OWNED_PROCESS_BARRIER']);marker.parent.mkdir(exist_ok=True);marker.write_text('{"blocked":true}')
 raise SystemExit(int(os.environ.get(status,'0')))
if len(args)>1 and args[1]=='get_app_container':print(os.environ['SYNTHETIC_APP' if args[-1]=='app' else 'SYNTHETIC_DATA'])
if len(args)>1 and args[1]=='addmedia':raise SystemExit(int(os.environ.get('SEED_STATUS','0')))
'''
    for name in ['xcrun','xcodebuild']:
        (binary/name).write_text(stub);(binary/name).chmod(0o755)
    scenarios=[(0,0,0,0,False),(13,0,0,0,False),(124,0,0,0,False),(0,7,0,0,False),(0,0,65,0,False),(0,0,0,65,False),(0,0,126,0,False),(13,0,65,0,False),(0,0,65,7,False),(0,0,65,126,False),(0,0,0,0,True)]
    profiles=[('QRCatcherUITests','PhoneUIResults.xcresult',360),
              ('QRCatcherUITests','CompactPhoneUIResults.xcresult',240),
              ('QRCatcherPadUITests','PadUIResults.xcresult',240)]
    # Mini now has its closed full-row/owned-destination executable suite.
    for test_class,result_name,file_cap in profiles:
      for seed,test_exit,file_exit,photo_exit,barrier in scenarios:
        observed=folder/'command.json';observed.unlink(missing_ok=True)
        marker=folder/'build/owned-process-cleanup.json';marker.unlink(missing_ok=True)
        result=subprocess.run(['bash','scripts/run_ios_platform_ui.sh','11111111-2222-4333-8444-555555555555',result_name,test_class],cwd=folder,
            env={**fixture_env,'PATH':str(binary)+':'+os.environ['PATH'],'SEED_STATUS':str(seed),'TEST_STATUS':str(test_exit),'FILE_STATUS':str(file_exit),'PHOTO_STATUS':str(photo_exit),'BARRIER_AFTER_FILES':str(barrier).lower(),'QRCATCHER_OWNED_PROCESS_BARRIER':str(marker),'GITHUB_WORKSPACE':str(folder),'OBSERVED_COMMAND':str(observed),'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data)},capture_output=True,text=True,timeout=15)
        expected=test_exit or (126 if file_exit==126 or barrier else seed or (126 if photo_exit==126 else file_exit or photo_exit))
        assert result.returncode==expected,(test_class,seed,test_exit,file_exit,photo_exit,result.returncode,result.stdout,result.stderr)
        rows=json.loads(observed.read_text());commands=[x['args'] for x in rows if x['tool']=='xcodebuild']
        expected_count=1 if test_exit else 2 if seed or file_exit==126 or barrier else 3
        assert len(commands)==expected_count,(test_class,commands)
        assert '-only-testing:QRCatcherUITests/'+test_class in commands[0]
        if test_class=='QRCatcherUITests':
            assert '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection' in commands[0]
            assert not any(v.startswith('-skip-testing:') for v in commands[0])
        else:
            assert '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' in commands[0]
            assert result_name.removesuffix('.xcresult')+'-layout.xcresult' in commands[0]
        attempts=[i for i,x in enumerate(rows) if 'addmedia' in x['args']]
        assert len(attempts)==(0 if test_exit or file_exit==126 or barrier else 1)
        if len(commands)>=2:
            bounded=[json.loads(line.split('BOUNDED_COMMAND_START ',1)[1]) for line in result.stdout.splitlines() if line.startswith('BOUNDED_COMMAND_START ')]
            file_commands=[row for row in bounded if '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' in row['command']]
            assert len(file_commands)==1
            assert file_commands[0]['seconds']==file_cap
            assert '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' in commands[1]
            assert result_name.removesuffix('.xcresult')+'-files.xcresult' in commands[1]
        if attempts:
            file_index=next(i for i,x in enumerate(rows) if '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' in x['args'])
            assert file_index<attempts[0]
        if len(commands)==3:
            assert not any('testRealFilesImportAndReopen' in v for v in commands[2])
            wanted='testRealPhotoImportReplacesSelectionAndPreservesBothRecords' if test_class=='QRCatcherPadUITests' else 'testRealPhotosImportAndReopen'
            assert any(v.endswith('/'+wanted) for v in commands[2])
        setup=json.loads((folder/'build/ios-platform-setup.json').read_text())
        assert setup['real_files_timeout_seconds']==file_cap
        assert setup['seed_attempts']==len(attempts) and setup['photo_seed_exit']==(-1 if not attempts else seed)
        assert setup['real_files_case_exit']==(-1 if test_exit else file_exit)
        assert setup['real_photo_case_exit']==(photo_exit if len(commands)==3 else -1)
        assert setup['timeout_does_not_prove_asset_absence'] is True
        print('SHELL_ARGUMENT_ROUTING_PASS',test_class,result_name,seed,test_exit,file_exit,photo_exit,barrier,'(command doubles only; no app runtime)',flush=True)

# The four real workflow result basenames must be retained by the exporter,
# including Files results when Photos was never executable.
exporter=ast.parse((root/'scripts/export_ios_platform_screenshots.py').read_text())
def exporter_inventory(tree):
    result_rows=[];log_names=[]
    for node in ast.walk(tree):
        if not (isinstance(node,ast.For) and isinstance(node.iter,ast.List)):continue
        result_target=(isinstance(node.target,ast.Tuple) and len(node.target.elts)==2 and
                       all(isinstance(value,ast.Name) for value in node.target.elts) and
                       [value.id for value in node.target.elts]==['result','label'])
        log_target=isinstance(node.target,ast.Name) and node.target.id=='name'
        if not (result_target or log_target):continue
        # Only the owned result/log inventories are literals. A matched dynamic
        # value remains an error; unrelated capacity/metadata loops are ignored.
        values=ast.literal_eval(node.iter)
        if result_target:result_rows=values
        elif 'ios-test-build.log' in values:log_names=values
    return result_rows,log_names

result_rows,log_names=exporter_inventory(exporter)
for basename,label in [('PhoneUIResults','pro-max'),('CompactPhoneUIResults','SE3'),('PadUIResults','ipad-pro-13'),('MiniUIResults','ipad-mini')]:
    assert (basename+'-files.xcresult',label+'-files') in result_rows
    assert basename+'-files.log' in log_names
print('FILES_RESULT_EXPORT_ROUTING_PASS four distinct workflow result bundles and logs',flush=True)
