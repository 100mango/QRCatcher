#!/usr/bin/env python3
"""Fail closed on the exact pinned source set and reader-only configuration."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'ThirdParty/ZXingCpp';manifest=json.loads((root/'source-manifest.json').read_text())
assert manifest['repository']=='https://github.com/zxing-cpp/zxing-cpp'
assert manifest['tag']=='v3.1.1' and manifest['commit']=='287c85df6f961c8efbfb5ffd736cd9457b8b890e'
assert manifest['writers'] is False and manifest['formats']==['QRCode']
for item in manifest['files']:
 path=root/item['path'];assert not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
 data=path.read_bytes();assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
config=root/manifest['configuration']['path'];assert hashlib.sha256(config.read_bytes()).hexdigest()==manifest['configuration']['sha256']
assert '#define ZXING_ENABLE_QRCODE 1' in config.read_text()
assert '#define ZXING_WRITERS' not in config.read_text()
for kind in ['1D','AZTEC','DATAMATRIX','MAXICODE','PDF417']:assert '#define ZXING_ENABLE_'+kind+' 0' in config.read_text()
assert (root/'LICENSE').is_file() and (root/'ThirdPartyNotices.txt').is_file()
print(json.dumps({'verified':True,'commit':manifest['commit'],'files':len(manifest['files']),'source_bytes':manifest['source_bytes']}),flush=True)
