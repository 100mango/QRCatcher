#!/usr/bin/env python3
import base64,hashlib,json,pathlib
root=pathlib.Path(__file__).resolve().parents[1]/'Tests/Fixtures'
for item in json.loads((root/'manifest.json').read_text()):
 data=base64.b64decode((root/(item['name']+'.base64')).read_text(),validate=False)
 assert hashlib.sha256(data).hexdigest()==item['sha256']
 (root/item['name']).write_bytes(data)
 print(item['name'],item['sha256'])
