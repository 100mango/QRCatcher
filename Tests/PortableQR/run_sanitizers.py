#!/usr/bin/env python3
"""Evaluate the exact production shim + pinned QR-only source, without downloads.
Requires existing gcc/g++, Python, Pillow and ReportLab. Does not install anything.
LeakSanitizer is disabled because the evaluation host is ptraced; ASan/UBSan remain fatal.
Outputs are bounded synthetic files beneath build/PortableQREvaluation.
"""
from pathlib import Path
import subprocess,json,os,time,hashlib
root=Path(__file__).resolve().parents[2];out=root/'build/PortableQREvaluation';out.mkdir(parents=True,exist_ok=True)
source=root/'ThirdParty/ZXingCpp';manifest=json.loads((source/'source-manifest.json').read_text())
subprocess.run(['python3',str(root/'scripts/verify_portable_source.py')],check=True)
subprocess.run(['python3',str(root/'Tests/PortableQR/generate_corpus.py')],check=True)
flags=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-DZXING_INTERNAL','-DZUECI_EMBED_NO_TO_ECI','-I'+str(source/'src'),'-I'+str(source/'Config'),'-I'+str(root/'Shared/PortableQR')]
subprocess.run(['gcc','-std=c99',*flags,'-c',str(source/'src/libzueci/zueci.c'),'-o',str(out/'zueci.o')],check=True,timeout=180)
exe=out/'qr-evaluation'
subprocess.run(['g++','-std=c++20',*flags,*[str(source/p) for p in manifest['cpp_sources']],str(root/'Shared/PortableQR/QRPortableDecoder.cpp'),str(root/'Tests/PortableQR/harness.cpp'),str(out/'zueci.o'),'-pthread','-o',str(exe)],check=True,timeout=600)
rows=json.loads((out/'corpus/manifest.json').read_text());assert len(rows)==len(set(r['name'] for r in rows));results=[]
for row in rows:
 start=time.monotonic()
 run=subprocess.run([str(exe),str(out/'corpus'/row['name'])],text=True,capture_output=True,timeout=8,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 actual=[bytes.fromhex(line[8:]).decode('utf8') for line in run.stdout.splitlines() if line.startswith('PAYLOAD ')]
 ok=run.returncode==0 and not run.stderr
 if row.get('expected') is not None:ok &= sorted(actual)==sorted(row['expected'])
 if row.get('expected_rejection'):ok &= run.stdout.startswith('REJECTED_')
 if row.get('expected_limit_rejection'):ok = run.returncode==4 and run.stdout=='DECODE_ERROR -3\n' and not run.stderr and not actual
 result={'name':row['name'],'success':ok,'exit':run.returncode,'actual':actual,'stdout':run.stdout[:8192],'stderr':run.stderr[:8192],'seconds':round(time.monotonic()-start,4)};results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
report={'upstream_commit':manifest['commit'],'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],'binary_bytes':exe.stat().st_size,'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'asan':True,'ubsan':True,'leak_sanitizer':False,'cases':results}
(out/'sanitizer-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert all(r['success'] for r in results),'A decoder or sanitizer assertion failed'
print('ALL_BOUNDED_SANITIZER_CASES_PASSED',len(results),flush=True)
