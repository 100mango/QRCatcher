"""One disposable job's durable stop signal after uncertain owned-child cleanup."""
import json,os,sys
from pathlib import Path
from atomic_json import write_json

SETTINGS_DISCOVERY_FENCE_VERSION = 1
KEY='QRCATCHER_OWNED_CLEANUP_UNCONFIRMED'
PATH_KEY='QRCATCHER_OWNED_PROCESS_BARRIER'

def barrier_path():
    value=os.environ.get(PATH_KEY)
    if not value:return None
    path=Path(value)
    root=Path(os.environ.get('GITHUB_WORKSPACE',Path.cwd())).resolve()
    if not path.is_absolute() or path!=root/'build'/'owned-process-cleanup.json':
        raise ValueError('Owned-process barrier must be this checkout build marker')
    return path

def blocked(command=None):
    if os.environ.get(KEY)=='true':return True
    try:
        path=barrier_path()
        if path is not None and (path.exists() or path.is_symlink()):return True
        root=Path(os.environ.get('GITHUB_WORKSPACE',Path.cwd())).resolve()
        mini=sys.modules.get('ipad_mini_setup')
        mini_pending=root/'build'/'ipad-mini-inflight.json'
        mini_stop=root/'build'/'ipad-mini-row-dispatched.json'
        mini_host=root/'build'/'ipad-mini-host-inflight.json'
        if mini is not None and mini.active_claim_exists():
            if not mini.active_claim_is_current(command):return True
        elif any(p.exists() or p.is_symlink() for p in [mini_pending,mini_stop,mini_host]):return True
        fixture_pending=root/'build'/'fixture-query-inflight.json'
        if fixture_pending.exists() or fixture_pending.is_symlink():return True
        discovery=sys.modules.get('settings_discovery_fence')
        discovery_active=discovery is not None and discovery.active_claim_exists()
        discovery_pending=root/'build'/'settings-discovery-inflight.json'
        if discovery_active and not discovery.active_claim_is_current(command):return True
        if not discovery_active and (discovery_pending.exists() or discovery_pending.is_symlink()):return True
        # A claimed latch disappearing is uncertainty, never permission. The
        # controller's held identity must be consulted before path existence.
        controller=sys.modules.get('vision_command_fence')
        if controller is not None and controller.active_claim_exists():
            return not controller.active_claim_is_current(command)
        root=Path(os.environ.get('GITHUB_WORKSPACE',Path.cwd())).resolve()
        pending=root/'build'/'vision-command-inflight.json'
        if pending.exists() or pending.is_symlink():
            # Only the validated controller for this exact direct command may
            # enter. Other interpreters and generic barrier checks stay blocked.
            from vision_command_fence import active_claim_is_current
            return not active_claim_is_current(command)
        return False
    except (OSError,ValueError,ImportError):return True

def mark_unconfirmed(operation):
    os.environ[KEY]='true'
    # The workflow variable blocks later steps; the atomic file also blocks
    # later commands in this same shell, whose environment cannot be changed.
    env_file=os.environ.get('GITHUB_ENV')
    if env_file:
        with open(env_file,'a') as output:output.write(KEY+'=true\n')
    path=barrier_path()
    if path:
        path.parent.mkdir(exist_ok=True)
        if path.exists() or path.is_symlink():return
        value={key:operation[key] for key in ['state','exit','original_exit','cleanup_confirmed'] if key in operation}
        write_json(path,{'blocked':True,'operation':value,'recovery':'Disposable VM teardown; no further compiler, simulator or test mutation'},limit=2048)

if __name__=='__main__':
    if sys.argv[1:]!=['--check']:raise SystemExit('Expected --check')
    if blocked():raise SystemExit(126)
