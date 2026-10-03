#!/usr/bin/env python3
"""Stage one public synthetic PNG in the disposable Debug app's own Files folder.
Never write Photos databases, another app container, personal files or Release.
"""
import hashlib,json,plistlib,subprocess,sys,uuid
from pathlib import Path
udid=str(uuid.UUID(sys.argv[1])).upper()
app_id='100mango.QRCatcher'
def container(kind):
    path=Path(subprocess.check_output(['xcrun','simctl','get_app_container',udid,app_id,kind],text=True,timeout=30).strip())
    assert path.is_dir() and not path.is_symlink()
    return path
info=plistlib.loads((container('app')/'Info.plist').read_bytes())
assert info['CFBundleIdentifier']==app_id and info.get('UIFileSharingEnabled') is True
assert info.get('LSSupportsOpeningDocumentsInPlace') is True
root=container('data');folder=root/'Documents/QRCatcher-Test-Imports'
for part in [root/'Documents',folder]:
    assert not part.is_symlink();part.mkdir(exist_ok=True)
file=folder/'SyntheticQR.png';assert not file.is_symlink()
source=Path('Tests/Fixtures/unicode.png').read_bytes();assert len(source)<128*1024
if file.exists():assert file.read_bytes()==source,'Never replace an unexpected existing document'
else:file.write_bytes(source)
assert file.read_bytes()==source
report={'scope':'Synthetic input in disposable Debug app-owned Documents folder, selected by actual Files UI',
        'file':file.name,'bytes':len(source),'sha256':hashlib.sha256(source).hexdigest(),'bundle':app_id,'device':udid}
out=Path('build/import-fixture');out.mkdir(exist_ok=True,parents=True);(out/'fixture.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
