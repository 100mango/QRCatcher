"""Publish a small complete JSON document atomically within its existing directory."""
import json,os,uuid
from pathlib import Path

def write_json(path,value,limit=64*1024):
    path=Path(path);assert path.parent.is_dir() and not path.is_symlink()
    data=(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
    if len(data)>limit:raise ValueError('Bounded JSON document exceeds its cap')
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
