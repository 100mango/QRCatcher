#!/usr/bin/env python3
"""Exercise shell argument routing using isolated command doubles, not app tests.
Runs the actual launcher on the host's Bash, including macOS Bash 3.2 in CI.
No simulator is touched; PATH overrides exist only in this child process.
"""
from pathlib import Path
import json,os,shutil,subprocess,tempfile

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='qrcatcher-launcher-routing-') as directory:
    folder=Path(directory);binary=folder/'bin';binary.mkdir();(folder/'scripts').mkdir()
    for name in ['run_ios_platform_ui.sh','run_bounded.py']:
        shutil.copyfile(root/'scripts'/name,folder/'scripts'/name)
    (binary/'xcrun').write_text('#!/bin/sh\nif [ "$2" = addmedia ]; then exit "${SEED_STATUS:-0}"; fi\nexit 0\n')
    (binary/'xcrun').chmod(0o755)
    (binary/'xcodebuild').write_text('#!/usr/bin/env python3\nimport sys,json,os\nfrom pathlib import Path\nPath(os.environ["OBSERVED_COMMAND"]).write_text(json.dumps(sys.argv[1:]))\n')
    (binary/'xcodebuild').chmod(0o755)
    for test_class,seed in [('QRCatcherUITests',0),('QRCatcherPadUITests',0),('QRCatcherPadUITests',13)]:
        observed=folder/'command.json';observed.unlink(missing_ok=True)
        result=subprocess.run(['bash','scripts/run_ios_platform_ui.sh','SYNTHETIC-DEVICE','SyntheticResults.xcresult',test_class],
            cwd=folder,env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'SEED_STATUS':str(seed),'OBSERVED_COMMAND':str(observed)},
            capture_output=True,text=True,timeout=10)
        assert result.returncode==seed,(test_class,result.stdout,result.stderr)
        command=json.loads(observed.read_text())
        assert '-only-testing:QRCatcherUITests/'+test_class in command
        assert any(value.startswith('-skip-testing:') for value in command)==(seed!=0)
        print('SHELL_ARGUMENT_ROUTING_PASS',test_class,seed,'(command doubles only; no app runtime)',flush=True)
