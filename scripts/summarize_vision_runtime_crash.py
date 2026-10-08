#!/usr/bin/env python3
"""Retain only a few crash-cause fields for the observed simulator component.
Never upload crash reports, thread stacks, memory, machine IDs or other reports.
"""
import json,pathlib
reports=[]
folder=pathlib.Path.home()/'Library/Logs/DiagnosticReports'
for path in sorted(folder.glob('RealityWidgets*.ips'))[-3:]:
 if path.stat().st_size>2*1024*1024:
  reports.append({'process':'RealityWidgets','observation':'report exceeds bounded parser limit'});continue
 decoder=json.JSONDecoder();remaining=path.read_text(errors='replace');objects=[]
 try:
  while remaining.strip():
   value,end=decoder.raw_decode(remaining.lstrip());objects.append(value);remaining=remaining.lstrip()[end:]
 except ValueError:
  reports.append({'process':'RealityWidgets','observation':'report format could not be parsed'});continue
 for obj in objects:
  if not isinstance(obj,dict) or obj.get('procName')!='RealityWidgets':continue
  item={'process':'RealityWidgets','architecture':obj.get('cpuType'),'translated':obj.get('translated')}
  for group,keys in [('exception',['type','signal','codes']),('termination',['namespace','code','indicator'])]:
   value=obj.get(group,{})
   if isinstance(value,dict):item[group]={k:(v[:256] if isinstance(v,str) else v) for k,v in value.items() if k in keys and isinstance(v,(str,int,bool))}
  reports.append(item)
out=pathlib.Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
data=json.dumps({'realitywidgets_reports':reports,'scope':'synthetic runner; process/exception/signal/architecture fields only'},indent=2)+'\n'
assert len(data.encode())<8192
(out/'realitywidgets-crash-summary.json').write_text(data);print(data,flush=True)
