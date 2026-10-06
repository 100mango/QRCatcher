#!/usr/bin/env python3
"""Resolve real installed device IDs; only the missing SE3 device is created."""
import json,os,subprocess
if os.environ.get('EVIDENCE_SCOPE') == 'ipad_mini':
 from ipad_mini_setup import configure
 configure()
 raise SystemExit(0)
raw=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j']))
rows=[d for runtime,devices in raw['devices'].items() if runtime.endswith('iOS-27-0') for d in devices]
def select(predicate):
 matches=[d for d in rows if predicate(d['name'])]
 assert matches,'Required simulator type is unavailable'
 return matches[0]['udid']
large=select(lambda n:n.startswith('iPhone') and 'Pro Max' in n)
pad=select(lambda n:n.startswith('iPad Pro 13-inch'))
mini=select(lambda n:n.startswith('iPad mini'))
types=json.loads(subprocess.check_output(['xcrun','simctl','list','devicetypes','-j']))['devicetypes']
compactType=next(t for t in types if t['name']=='iPhone SE (3rd generation)')
runtimes=json.loads(subprocess.check_output(['xcrun','simctl','list','runtimes','-j']))['runtimes']
runtime=next(r for r in runtimes if r['identifier'].endswith('iOS-27-0') and r.get('isAvailable'))
compact=subprocess.check_output(['xcrun','simctl','create','QRCatcher Compact SE3',compactType['identifier'],runtime['identifier']],text=True).strip()
values={'SIMULATOR_ID':large,'COMPACT_SIMULATOR_ID':compact,'IPAD_SIMULATOR_ID':pad,'MINI_SIMULATOR_ID':mini}
print(json.dumps(values,indent=2))
with open(os.environ['GITHUB_ENV'],'a') as f:
 for key,value in values.items():f.write(key+'='+value+'\n')
