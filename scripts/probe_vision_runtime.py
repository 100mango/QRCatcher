#!/usr/bin/env python3
"""Bounded real simulator boot on the existing standard runner; no downloads.
The JSON distinguishes runtime readiness from app launch/decode test success.
"""
import json,os,pathlib,signal,subprocess,time
out=pathlib.Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
report={'stage':'runtime_boot','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'ready':False}
def run(arguments,timeout):
 p=subprocess.Popen(arguments,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
 try:
  output,_=p.communicate(timeout=timeout);return p.returncode,output
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM)
  try:output,_=p.communicate(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);output,_=p.communicate()
  return 124,output+'\nBOUNDED_TIMEOUT\n'
try:
 devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j'],timeout=30))
 candidates=[(runtime,d) for runtime,rows in devices['devices'].items() if runtime.endswith('xrOS-27-0') for d in rows]
 if not candidates:raise RuntimeError('No available installed visionOS27 simulator device was discovered')
 runtime,device=candidates[0];report.update(runtime=runtime,device=device)
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('VISION_SIMULATOR_ID='+device['udid']+'\n')
 boot_code,boot=run(['xcrun','simctl','boot',device['udid']],180)
 status_code,status=run(['xcrun','simctl','bootstatus',device['udid'],'-b'],420)
 (out/'boot.log').write_text((boot+'\n'+status)[-512*1024:])
 report.update(boot_exit=boot_code,bootstatus_exit=status_code)
 if status_code!=0:raise RuntimeError('Installed visionOS simulator did not finish booting within the supported bounded route')
 service_code,services=run(['xcrun','simctl','spawn',device['udid'],'launchctl','print','system'],30)
 (out/'services-tail.log').write_text(services[-128*1024:]);report['services_exit']=service_code
 if service_code!=0:raise RuntimeError('Booted simulator did not respond to its system service manager')
 report['ready']=True
except Exception as error:report['environment_observation']=str(error)
finally:
 (out/'runtime.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('VISION_READY='+str(report['ready']).lower()+'\n')

if not report["ready"]:raise SystemExit("Vision runtime readiness was not established; see runtime.json. This is not an app-test result.")
