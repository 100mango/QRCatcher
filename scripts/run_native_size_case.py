#!/usr/bin/env python3
"""Run one existing native UI case at an actually read-back system text size."""
import json,math,sys
from pathlib import Path
from simulator_content_size import probe,validate_ui_command
from owned_process_barrier import mark_unconfirmed
from atomic_json import write_json
from watch_process import execute

CONFIG={
 'watch':('Watch','watchOS Simulator','testFixtureFedOfflineResultSourceImageAndRelaunch',240,'build/watch-runtime/system-content-size.json','WatchLargestUIResults.xcresult'),
 'vision':('Vision','visionOS Simulator','testChineseEmptyPhotosResultAndOfflinePolicy',300,'build/vision-runtime/system-content-size.json','VisionLargestUIResults.xcresult'),
 'tv':('TV','tvOS Simulator','testExplicitlyPreconditionedPhotosDecodeExportAndReopen',420,'build/native-release-evidence/tv-system-content-size.json','TVLargestUIResults.xcresult'),
}

def run_case(platform,device,precondition=True):
 label,destination,case,cap,report_file,result=CONFIG[platform]
 root=Path.cwd().resolve();target='QRCatcher'+label+'UITests';scheme='QRCatcher'+label
 command=['xcodebuild','test-without-building','-project',str(root/'QRCatcher.xcodeproj'),'-scheme',scheme,
  '-configuration','Debug','-derivedDataPath',str(root/'build'/(label+'Tests')),
  '-destination','platform='+destination+',id='+device,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
  '-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','240',
  '-only-testing:'+target+'/'+target+'/'+case,'-resultBundlePath',str(root/result),'CODE_SIGNING_ALLOWED=NO']
 contract=dict(root=str(root),project='QRCatcher.xcodeproj',scheme=scheme,derived_data='build/'+label+'Tests',test_bundle=target,platform=destination)
 path=root/report_file;path.parent.mkdir(parents=True,exist_ok=True)
 try:report=probe(device,path,command if precondition else None,cap,expected_ui=contract if precondition else None)
 except (OSError,ValueError,RuntimeError) as error:
  report={'status':'contract_or_execution_unresolved','error_type':type(error).__name__,'message':str(error)[:1024]}
  mark_unconfirmed({'state':report['status'],'exit':126,'cleanup_confirmed':False})
  path.write_text(json.dumps(report,indent=2)+'\n');return 126,report
 if report.get('cleanup_unconfirmed') or report['status']=='restore_readback_failed':
  mark_unconfirmed({'state':report['status'],'exit':126,'cleanup_confirmed':False});return 126,report
 if platform in {'watch','tv'} and precondition and report['status']=='original_value_not_recognized' and report.get('original_raw')=='unsupported':
  # This exact completed read-only response is retained. A public SwiftUI
  # trait override tests rendering only; it cannot qualify system propagation.
  trait_case,trait_cap,trait_result,proof_prefix={'watch':('testFixtureResultAndRelaunchAtLargestPublicTrait',240,'WatchTraitStressUIResults.xcresult','WATCH_PUBLIC_TRAIT_PROOF '),'tv':('testPreconditionedPhotosWorkflowAtLargestPublicTrait',420,'TVTraitStressUIResults.xcresult','TV_PUBLIC_TRAIT_PROOF ')}[platform]
  trait_command=command.copy()
  trait_command[trait_command.index('-only-testing:'+target+'/'+target+'/'+case)]='-only-testing:'+target+'/'+target+'/'+trait_case
  trait_command[trait_command.index('-resultBundlePath')+1]=str(root/trait_result)
  stress={'scope':'DEBUG public SwiftUI largest-trait layout stress; not a system setting','system_setting_propagation':False,'state':'starting'}
  report['layout_stress']=stress;write_json(path,report)
  cleanup_known=False
  try:
   validate_ui_command(trait_command,device,contract)
   code,output,operation=execute(trait_command,trait_cap)
   stress.update(exit=code,operation=operation,state='finished')
   if code==126 or operation.get('cleanup_confirmed') is not True:
    mark_unconfirmed(operation);stress['state']='cleanup_unconfirmed';write_json(path,report);return 126,report
   cleanup_known=True
   proofs=[json.loads(line[len(proof_prefix):]) for line in output.splitlines() if line.startswith(proof_prefix)]
   verified=len(proofs)==1
   if verified:
    proof=proofs[0];keys=['baseline_body_metric','actual_body_metric','baseline_payload_height','actual_payload_height','viewport_width_points','viewport_height_points']
    verified=all(type(proof.get(key)) in (int,float) and math.isfinite(proof[key]) and proof[key]>0 for key in keys)
    verified=verified and proof.get('trait')=='accessibility5' and proof.get('system_setting_propagation') is False
    verified=verified and proof['actual_body_metric']>proof['baseline_body_metric'] and proof['actual_payload_height']>proof['baseline_payload_height']+1
    stress['measurements']=proof
   stress['rendering_proof_verified']=verified;stress['passed']=code==0 and verified
  except Exception as error:
   if not cleanup_known:
    mark_unconfirmed({'state':'layout_stress_execution_unresolved','exit':126,'cleanup_confirmed':False})
    stress.update(state='execution_unresolved',error_type=type(error).__name__);write_json(path,report);return 126,report
   stress.update(state='rendering_proof_invalid',passed=False,error_type=type(error).__name__)
  write_json(path,report)
  return 2,report # Keep the unavailable system-setting gate explicitly unqualified.
 return (0 if report['status']=='largest_ui_passed' and report.get('restore_verified') else 2),report

if __name__=='__main__':
 if len(sys.argv)!=3 or sys.argv[1] not in CONFIG:raise SystemExit('Expected watch|vision|tv and owned device UUID')
 code,report=run_case(sys.argv[1],sys.argv[2]);print(json.dumps(report),flush=True);raise SystemExit(code)
