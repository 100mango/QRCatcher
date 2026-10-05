"""Durable uncertainty marker around one inherited-group container query.

No new process session and no claim that a service daemon completed. An outer
owner may clean the inherited group; absent normal finalization, later commands
remain blocked until this disposable VM is discarded.
"""
import contextlib,json,os,stat,subprocess,sys
from pathlib import Path
from owned_process_barrier import blocked,mark_unconfirmed

NAME='fixture-query-inflight.json'

def signature(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)

@contextlib.contextmanager
def query_guard(command):
    if blocked():raise SystemExit(126)
    if (len(command)!=6 or command[:3]!=['xcrun','simctl','get_app_container'] or
            command[4]!='100mango.QRCatcher' or command[5] not in {'app','data'}):
        raise ValueError('Only the existing exact fixture-container query is permitted')
    root=Path(os.environ.get('GITHUB_WORKSPACE',Path.cwd())).resolve();parent=root/'build'
    if not parent.is_dir() or parent.resolve()!=parent or parent.is_symlink():
        raise ValueError('Expected real checkout build directory')
    directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    descriptor=None
    try:
        descriptor=os.open(NAME,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        raw=(json.dumps({'version':1,'state':'before_query','command':command,'owner_pid':os.getpid(),
                         'inherited_group':os.getpgrp(),'timeout_seconds':30,'host_group_cleanup_claimed':False},sort_keys=True)+'\n').encode()
        os.write(descriptor,raw);os.fsync(descriptor)
        original=signature(os.fstat(descriptor))
        print('FIXTURE_CONTAINER_QUERY_BEGIN kind='+command[5]+' inherited_group='+str(os.getpgrp()),flush=True)
        try:
            yield
            os.lseek(descriptor,0,os.SEEK_SET)
            if (os.read(descriptor,len(raw)+1)!=raw or signature(os.fstat(descriptor))!=original or
                    signature(os.stat(NAME,dir_fd=directory,follow_symlinks=False))!=original or
                    parent.resolve()!=parent or (parent.stat().st_dev,parent.stat().st_ino)!=(os.fstat(directory).st_dev,os.fstat(directory).st_ino)):
                raise ValueError('Owned fixture-query marker changed; do not clear uncertainty')
            os.unlink(NAME,dir_fd=directory)
            print('FIXTURE_CONTAINER_QUERY_END kind='+command[5]+' direct_child_exit=0 host_group_cleanup_claimed=false',flush=True)
        except BaseException as error:
            state='fixture_container_query_timeout' if isinstance(error,subprocess.TimeoutExpired) else 'fixture_container_query_unresolved'
            mark_unconfirmed({'state':state,'exit':126,'original_exit':124 if isinstance(error,subprocess.TimeoutExpired) else 1,'cleanup_confirmed':False})
            print('FIXTURE_CONTAINER_QUERY_UNCONFIRMED kind='+command[5]+' state='+state,file=sys.stderr,flush=True)
            raise SystemExit(126) from error
    finally:
        if descriptor is not None:os.close(descriptor)
        os.close(directory)
