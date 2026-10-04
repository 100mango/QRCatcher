#!/usr/bin/env python3
"""Exercise actual shell routing with isolated commands, never app runtime.
Runs the host Bash, including macOS Bash3.2 in CI; only disposable test files.
"""
from pathlib import Path
import json,os,plistlib,shutil,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='qrcatcher-launcher-routing-') as directory:
    folder=Path(directory);binary=folder/'bin';binary.mkdir();(folder/'scripts').mkdir()
    for name in ['run_ios_platform_ui.sh','run_bounded.py','watch_process.py','owned_process_group.py','owned_process_barrier.py','atomic_json.py','stage_owned_import_fixture.py']:
        shutil.copyfile(root/'scripts'/name,folder/'scripts'/name)
    app=folder/'synthetic-app';app.mkdir();data=folder/'synthetic-data';data.mkdir()
    (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'100mango.QRCatcher','UIFileSharingEnabled':True,'LSSupportsOpeningDocumentsInPlace':True}))
    (folder/'Tests/Fixtures').mkdir(parents=True)
    (folder/'Tests/Fixtures/unicode.png').write_bytes(b'Isolated routing-test bytes, not a decoded app fixture')
    stub='''#!/usr/bin/env python3
import sys,json,os
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
p=Path(os.environ['OBSERVED_COMMAND']);rows=json.loads(p.read_text()) if p.exists() else [];rows.append({'tool':name,'args':args});p.write_text(json.dumps(rows))
if name=='xcodebuild':raise SystemExit(int(os.environ.get('TEST_STATUS','0')))
if len(args)>1 and args[1]=='get_app_container':print(os.environ['SYNTHETIC_APP' if args[-1]=='app' else 'SYNTHETIC_DATA'])
if len(args)>1 and args[1]=='addmedia':raise SystemExit(int(os.environ.get('SEED_STATUS','0')))
'''
    for name in ['xcrun','xcodebuild']:
        (binary/name).write_text(stub);(binary/name).chmod(0o755)
    for test_class,seed,test_exit in [('QRCatcherUITests',0,0),('QRCatcherUITests',13,0),('QRCatcherUITests',0,7),('QRCatcherPadUITests',0,0),('QRCatcherPadUITests',13,0),('QRCatcherPadUITests',0,7)]:
        observed=folder/'command.json';observed.unlink(missing_ok=True)
        result=subprocess.run(['bash','scripts/run_ios_platform_ui.sh','11111111-2222-4333-8444-555555555555','SyntheticResults.xcresult',test_class],cwd=folder,
            env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'SEED_STATUS':str(seed),'TEST_STATUS':str(test_exit),'OBSERVED_COMMAND':str(observed),'SYNTHETIC_APP':str(app),'SYNTHETIC_DATA':str(data)},capture_output=True,text=True,timeout=15)
        assert result.returncode==(test_exit or seed),(test_class,result.stdout,result.stderr)
        rows=json.loads(observed.read_text());commands=[x['args'] for x in rows if x['tool']=='xcodebuild']
        assert len(commands)==(2 if seed==0 and test_exit==0 else 1)
        assert '-only-testing:QRCatcherUITests/'+test_class in commands[0]
        if test_class=='QRCatcherUITests':
            assert '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealPickerWarmupAndCancelPreservesPreviousSelection' in commands[0]
            assert not any(v.startswith('-skip-testing:') for v in commands[0])
        else:
            assert '-skip-testing:QRCatcherUITests/QRCatcherPadUITests/testRealPhotoImportReplacesSelectionAndPreservesBothRecords' in commands[0]
            assert 'SyntheticResults-layout.xcresult' in commands[0]
        attempts=[i for i,x in enumerate(rows) if 'addmedia' in x['args']]
        assert len(attempts)==(0 if test_exit else 1)
        if attempts:assert next(i for i,x in enumerate(rows) if x['tool']=='xcodebuild')<attempts[0]
        if len(commands)==2:assert '-only-testing:QRCatcherUITests/QRCatcherImageImportUITests/testRealFilesImportAndReopen' in commands[1]
        setup=json.loads((folder/'build/ios-platform-setup.json').read_text())
        assert setup['seed_attempts']==len(attempts) and setup['photo_seed_exit']==(-1 if test_exit else seed)
        assert setup['timeout_does_not_prove_asset_absence'] is True
        print('SHELL_ARGUMENT_ROUTING_PASS',test_class,seed,test_exit,'(command doubles only; no app runtime)',flush=True)
