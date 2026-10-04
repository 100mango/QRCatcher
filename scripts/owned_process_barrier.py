"""One disposable job's durable stop signal after uncertain owned-child cleanup."""
import json,os,sys
from pathlib import Path
from atomic_json import write_json

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

def blocked():
    if os.environ.get(KEY)=='true':return True
    try:
        path=barrier_path()
        return path is not None and (path.exists() or path.is_symlink())
    except (OSError,ValueError):return True

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
