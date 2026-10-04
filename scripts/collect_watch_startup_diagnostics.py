#!/usr/bin/env python3
"""Read-only, bounded diagnostics for this disposable Watch test startup.
No service restart, TCC edit, permission grant, stack dump or credential capture.
"""
import json,re,sys,uuid
from watch_process import execute
from owned_process_barrier import blocked,mark_unconfirmed
from pathlib import Path

udid=str(uuid.UUID(sys.argv[1])).upper();out=Path('build/watch-runtime');out.mkdir(parents=True,exist_ok=True)
stage=sys.argv[2] if len(sys.argv)>2 else 'hosted';assert stage in ['hosted','ui']
report={'device':udid,'scope':'synthetic Watch startup; app/testmanager errors and bounded crash-cause fields','crashes':[]}
predicate='process == "QRCatcherWatch" OR process == "testmanagerd" OR process == "xctest"'
command=['xcrun','simctl','spawn',udid,'log','show','--last','4m','--style','compact','--predicate',predicate]
try:
    code,output,operation=execute(command,25,output_limit=256*1024,tail_limit=32*1024,echo=False)
    report['log_exit']=code;report['log_operation']=operation
    if code==126 or operation.get('cleanup_confirmed') is not True:
        report['cleanup_unconfirmed']=True;mark_unconfirmed(operation)
    # Keep only relevant launch/error lines. Exclude credential-looking entries
    # and never retain a full simulator or machine log.
    lines=[line[:1200] for line in output.splitlines()
        if re.search(r'error|fail|launch|attach|timeout|connection|bootstrap',line,re.I)
        and not re.search(r'token|secret|password|credential|authorization',line,re.I)]
    report['startup_events']='\n'.join(lines[-60:])[-16*1024:]
except (OSError,RuntimeError):
    report['log_exit']=124;report['startup_events']='The read-only scoped log query timed out'
folder=Path.home()/'Library/Logs/DiagnosticReports'
for pattern in ['QRCatcherWatch*.ips','testmanagerd*.ips','xctest*.ips']:
    for path in sorted(folder.glob(pattern))[-2:]:
        if path.is_symlink() or path.stat().st_size>2*1024*1024:continue
        remaining=path.read_text(errors='replace');decoder=json.JSONDecoder()
        while remaining.strip():
            try:value,end=decoder.raw_decode(remaining.lstrip());remaining=remaining.lstrip()[end:]
            except ValueError:break
            if not isinstance(value,dict) or value.get('procName') not in ['QRCatcherWatch','testmanagerd','xctest']:continue
            row={'process':value['procName'],'architecture':value.get('cpuType'),'translated':value.get('translated')}
            for group,keys in [('exception',['type','signal','codes']),('termination',['namespace','code','indicator'])]:
                fields=value.get(group,{})
                if isinstance(fields,dict):row[group]={k:(v[:256] if isinstance(v,str) else v) for k,v in fields.items() if k in keys and isinstance(v,(str,int,bool))}
            report['crashes'].append(row)
data=json.dumps(report,indent=2)+'\n';assert len(data.encode())<32*1024
(out/(stage+'-startup-diagnostics.json')).write_text(data);print(data,flush=True)
if report.get('cleanup_unconfirmed') or blocked():raise SystemExit(126)
