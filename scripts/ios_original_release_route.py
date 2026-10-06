#!/usr/bin/env python3
"""One closed original iPhone/iPad qualification route; never Store submission."""
import hashlib,json,os,re,sys
from pathlib import Path
from atomic_json import write_json
from ios_import_continuation import read_regular
from diagnostic_mini_managed_route import job_parts,split_platform,step_name
from owned_process_barrier import blocked,mark_unconfirmed
from watch_process import execute

REPOSITORY='100mango/QRCatcher'
BRANCH='codex/ios-original-release'
REF='refs/heads/'+BRANCH
WORKFLOW='.github/workflows/ios-original-release.yml'
WORKFLOW_REF=REPOSITORY+'/'+WORKFLOW+'@'+REF
PROJECT='QRCatcher-iOS-Only.xcodeproj'
SCHEME='QRCatcher'
CANONICAL='.github/workflows/apple-platforms.yml'
CANONICAL_SHA256='1c3b0759c211b54ec30bd8d19cac9e7a4f03b77dea94ae81146910f10ff202d4'
SCOPES=('iphone_pro','iphone_se3','ipad_pro','ipad_mini')
RECEIPT=Path('build/ios-original-release-provenance.json')
INITIAL_HASH_KEY='QRCATCHER_IOS_ORIGINAL_INITIAL_PROVENANCE_SHA256'
SELECTED_STEPS=(
 'Capture original Mini job clock before checkout',
 'Checkout Mini exact source with bounded main and post',
 'checkout',
 'Verify Mini exact source inside original job budget',
 'Verify exact source and stable toolchain',
 'Compile Mini tests inside original job budget',
 'Compile iOS tests before this device boots',
 'Configure one newly owned Mini without manual boot or install',
 'Select this fresh VM phone or iPad device',
 'Run iOS codec equivalence and existing unit regression',
 'Run large-phone UI regression',
 'Run compact-phone UI regression',
 'Run native 13-inch iPad workflows',
 'Run native iPad mini workflows',
 'Export bounded complete Mini row evidence',
 'Export bounded phone and iPad evidence',
 'Validate Mini and whole-run evidence allocation',
 'Validate isolated platform and whole-run evidence allocation',
 'Admit complete Mini artifact action inside original clock',
 'Retain small phone and iPad evidence',
 'Observe Mini artifact action without claiming host-group cleanup',
 'Summarize all four Mini cases from exact exported results',
 'Summarize executed evidence',
 'Verify final Mini source while preserving checkout-post reserve',
 'Verify source stayed unchanged')
SOURCE_DEPENDENT_STEPS=(
 'Compile iOS tests before this device boots','Select this fresh VM phone or iPad device',
 'Run iOS codec equivalence and existing unit regression','Run large-phone UI regression',
 'Run compact-phone UI regression','Run native 13-inch iPad workflows')


def require(value,message):
 if not value:raise ValueError(message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def replace_once(text,before,after):
 require(text.count(before)==1,'Missing or repeated selected source clause')
 return text.replace(before,after,1)


def render_workflow(canonical):
 require(digest(canonical.encode())==CANONICAL_SHA256,'Canonical all-platform workflow changed')
 preflight,platform=job_parts(canonical);header,steps,tail=split_platform(platform)
 selected=[s for s in steps if step_name(s) in SELECTED_STEPS]
 require(tuple(step_name(s) for s in selected)==SELECTED_STEPS,'Missing/reordered/duplicate original iOS step')
 for index,step in enumerate(selected):
  if step_name(step)=='Verify exact source and stable toolchain':
   selected[index]=replace_once(step,'    - name: Verify exact source and stable toolchain\n',
    '    - name: Verify exact source and stable toolchain\n      id: ios_original_source\n')
  elif step_name(step) in SOURCE_DEPENDENT_STEPS:
   condition=re.search(r'^      if: (.*) }}$',step,re.M)
   require(condition is not None,'Selected native source dependency condition missing')
   selected[index]=step[:condition.end(1)]+" && steps.ios_original_source.outcome == 'success'"+step[condition.end(1):]
 preflight=replace_once(preflight,'        test "$GITHUB_REF" = refs/heads/codex/apple-platforms\n',
  '        python3 scripts/ios_original_release_route.py validate\n')
 preflight=replace_once(preflight,'        python3 scripts/generate_project.py\n',
  '        python3 scripts/generate_project.py --profile ios-only\n')
 preflight=replace_once(preflight,'        git diff --exit-code -- QRCatcher.xcodeproj\n',
  '        git diff --exit-code -- QRCatcher.xcodeproj '+PROJECT+'\n')
 preflight=replace_once(preflight,'Build all test schemes and verify actual Debug Watch embedding',
  'Compile original iOS tests and verify unsigned Release archive isolation')
 preflight=replace_once(preflight,'python3 -u scripts/compile_platform_preflight.py',
  'python3 -u scripts/compile_ios_original_preflight.py')
 preflight=replace_once(preflight,'    - name: Verify preflight source stayed unchanged\n',
  "    - name: Retain bounded unsigned iOS package proof\n"
  "      id: ios_package_evidence\n      timeout-minutes: 1\n"
  "      if: ${{ always() && env.QRCATCHER_IOS_ORIGINAL_INITIAL_PROVENANCE_SHA256 != '' }}\n"
  "      run: python3 scripts/ios_original_release_route.py collect-preflight\n"
  "    - name: Upload bounded unsigned iOS package proof\n      timeout-minutes: 1\n"
  "      if: ${{ always() && steps.ios_package_evidence.outcome == 'success' }}\n"
  "      uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n"
  "      with:\n        name: qrcatcher-ios-original-package-evidence\n"
  "        path: build/ios-original-preflight-evidence\n        retention-days: 1\n"
  "        compression-level: 9\n        if-no-files-found: error\n"
  "    - name: Verify preflight source stayed unchanged\n")
 header=replace_once(header,'    timeout-minutes: 45\n',
  "    timeout-minutes: ${{ matrix.scope == 'ipad_mini' && 50 || 45 }}\n")
 body=header+''.join(selected)
 body=replace_once(body,'      timeout-minutes: 27\n','      timeout-minutes: 32\n')
 body=replace_once(body,"'mini':1620","'mini':1920")
 old="        require(os.environ['GITHUB_REF']=='refs/heads/codex/apple-platforms')\n"
 new=("        require(os.environ['GITHUB_REF']=='"+REF+"')\n"
  "        require(os.environ.get('GITHUB_WORKFLOW_REF')=='"+WORKFLOW_REF+"')\n"
  "        require(os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('IOS_FIRST_RELEASE_CANDIDATE_ONLY')=='true')\n"
  "        require(os.environ.get('GITHUB_JOB')=='platform' and os.environ.get('EVIDENCE_SCOPE')=='ipad_mini')\n")
 body=replace_once(body,old,new)
 body=body.replace('python3 scripts/generate_project.py\n','python3 scripts/generate_project.py --profile ios-only\n')
 body=body.replace('git diff --exit-code -- QRCatcher.xcodeproj\n','git diff --exit-code -- QRCatcher.xcodeproj '+PROJECT+'\n')
 body=body.replace('-project QRCatcher.xcodeproj','-project '+PROJECT)
 body=replace_once(body,'python3 scripts/verify_embedded_watch.py simulator',
  'python3 -u scripts/run_bounded.py 20 python3 scripts/ios_original_release_route.py debug-package')
 body=replace_once(body,'        name: qrcatcher-${{ matrix.scope }}-evidence\n',
  '        name: qrcatcher-ios-original-${{ matrix.scope }}-evidence\n')
 body=replace_once(body,
  "        echo 'Runtime proof requires successful Mac XCTest; x86_64 build is separate from runtime proof. Physical camera capture/denial/disconnect and paired Watch background file transport remain physical-device gates; exact sandbox/platform outcomes are reported separately.' >> \"$GITHUB_STEP_SUMMARY\"\n",
  "        echo 'Original iPhone/iPad qualification requires this exact isolated app/archive and all selected iOS cases. Physical camera capture, denial and recovery remain device checks; signing/submission are separate. Deferred platform results are reported separately.' >> \"$GITHUB_STEP_SUMMARY\"\n")
 # The selected phone/iPad shell commands, hosted selectors, fixtures, audits,
 # native case allowances and device/process gates otherwise remain unchanged.
 body=body.replace('test "$GITHUB_REF" = refs/heads/codex/apple-platforms',
                   'python3 scripts/ios_original_release_route.py validate')
 prefix=("name: Original iPhone and iPad release qualification\npermissions:\n  contents: read\n"
  "concurrency:\n  group: qrcatcher-apple-platforms\n  cancel-in-progress: false\n"
  "env:\n  IOS_FIRST_RELEASE_CANDIDATE_ONLY: 'true'\njobs:\n")
 strategy=("    name: ${{ matrix.scope }} · original iOS qualification\n"
  "    strategy:\n      fail-fast: false\n      max-parallel: 1\n"
  "      matrix:\n        scope:\n"+''.join('        - '+s+'\n' for s in SCOPES))
 return prefix+preflight+'  platform:\n'+body+strategy+"'on':\n  push:\n    branches:\n    - "+BRANCH+'\n'


def current_identity():
 canonical=read_regular(CANONICAL,128*1024).decode();workflow=read_regular(WORKFLOW,128*1024).decode()
 require(workflow==render_workflow(canonical),'Closed original iOS workflow differs')
 e=os.environ;sha=e.get('GITHUB_SHA','')
 require(re.fullmatch('[0-9a-f]{40}',sha) is not None and e.get('GITHUB_WORKFLOW_SHA')==sha,'Wrong source/workflow SHA')
 require(e.get('GITHUB_REPOSITORY')==REPOSITORY and e.get('GITHUB_REF')==REF and e.get('GITHUB_WORKFLOW_REF')==WORKFLOW_REF,'Wrong original iOS repository/ref/workflow')
 require(e.get('GITHUB_EVENT_NAME')=='push' and e.get('IOS_FIRST_RELEASE_CANDIDATE_ONLY')=='true','Closed original iOS push required')
 require(e.get('RUNNER_OS')=='macOS' and e.get('RUNNER_ARCH')=='ARM64','Wrong standard Mac architecture')
 job=e.get('GITHUB_JOB');scope=e.get('EVIDENCE_SCOPE','')
 require((job=='preflight' and scope=='') or (job=='platform' and scope in SCOPES),'Wrong original iOS job/scope')
 require(all(re.fullmatch('[1-9][0-9]{0,19}',e.get(k,'')) for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')),'Wrong run/attempt identity')
 return {'version':1,'release_candidate_only':True,'release_qualification':False,'repository':REPOSITORY,
  'source_sha':sha,'workflow_sha':sha,'ref':REF,'workflow_ref':WORKFLOW_REF,
  'workflow_sha256':digest(workflow.encode()),'canonical_workflow_sha256':CANONICAL_SHA256,
  'run_id':e['GITHUB_RUN_ID'],'run_attempt':e['GITHUB_RUN_ATTEMPT'],'job':job,'scope':scope,
  'selected_scopes':list(SCOPES),'project':PROJECT,'scheme':SCHEME,'shipping_watch_requested':False,
  'maximum_simultaneous_slots':1,'cancel_in_progress':False,'permissions':{'contents':'read'},
  'mini_row_seconds':1920,'mini_job_seconds':3000,'first_mini_summary_seconds':30,
  'required_unit_cases':30,'required_phone_cases':{'ordinary':9,'files':1,'photos':1},
  'required_pad_cases':{'layout':2,'files':1,'photos':1},
  'preflight_evidence_limit_bytes':1000000,'selected_runtime_evidence_limit_bytes':8000000}


def source_readback(source):
 record=current_identity()
 require(record['job']=='preflight' or record['scope']!='ipad_mini','No generic readback inside the managed Mini lease')
 require(os.environ.get('GITHUB_WORKSPACE')==str(Path.cwd()) and Path.cwd().resolve(strict=True)==Path.cwd(),'Actual source checkout required')
 def checked(command):
  require(not blocked(),'Source readback blocked by owned-process uncertainty')
  code,output,operation=execute(command,5,output_limit=4096,tail_limit=4096,echo=False)
  elapsed=operation.get('elapsed_seconds')
  timely=(type(elapsed) in (int,float) and 0<=elapsed<7)
  if operation.get('state')!='completed' or operation.get('cleanup_confirmed') is not True or not timely or code==126:
   mark_unconfirmed(operation);raise ValueError('Source readback incomplete, late or cleanup uncertain')
  require(code==0 and not blocked(),'Source readback failed or owned-process uncertainty')
  return output.strip()
 require(checked(['git','rev-parse','HEAD'])==source,'Source HEAD differs')
 tree=checked(['git','rev-parse','HEAD^{tree}']);require(re.fullmatch('[0-9a-f]{40}',tree),'Invalid source tree')
 checked(['git','diff','--exit-code','HEAD','--'])
 require(checked(['git','status','--porcelain=v1','--untracked-files=all'])=='','Initial checkout contains changes')
 return tree


def write_initial(record,tree,phase):
 require(re.fullmatch('[0-9a-f]{40}',tree),'Wrong prepared source tree')
 require(not RECEIPT.parent.is_symlink() and RECEIPT.parent.resolve()==Path.cwd()/RECEIPT.parent,'Real checkout receipt parent required')
 RECEIPT.parent.mkdir(exist_ok=True)
 record={**record,'tested_tree':tree,'source_readback_phase':phase}
 write_json(RECEIPT,record,limit=4096);fingerprint=digest(read_regular(RECEIPT,4096))
 environment=os.environ.get('GITHUB_ENV','');require(environment,'Missing runner job environment file')
 with open(environment,'a') as out:out.write(INITIAL_HASH_KEY+'='+fingerprint+'\n')
 os.environ[INITIAL_HASH_KEY]=fingerprint
 return record


def prepared(head,tree):
 record=current_identity();require(record['job']=='platform' and record['scope']=='ipad_mini' and head==record['source_sha'],'Wrong original Mini prepare identity')
 require(os.environ.get('GITHUB_WORKSPACE')==str(Path.cwd()) and Path.cwd().resolve(strict=True)==Path.cwd(),'Actual managed prepare checkout required')
 marker=Path('build/ipad-mini-host-inflight.json');before=read_regular(marker,4096);lease=json.loads(before)
 require(type(lease) is dict and type(lease.get('owner_pid')) is int and lease['owner_pid']>0 and
  lease=={'source':head,'workflow_sha':head,'run_id':record['run_id'],'run_attempt':record['run_attempt'],
          'scope':'ipad_mini','phase':'host-prepare','owner_pid':lease['owner_pid'],'command':['bash','scripts/ipad_mini_prepare.sh']},'Wrong owned prepare lease')
 record=write_initial(record,tree,'existing bounded managed Mini prepare HEAD/tree/diff')
 require(read_regular(marker,4096)==before,'Owned prepare marker changed during receipt retention')
 return record


def debug_package():
 # Pure inspection inside the already bounded owning controller/step; no
 # nested generic process is allowed inside a real Mini host lease.
 current_identity()
 products=Path('build/iOS/Build/Products')
 require(products.is_dir() and not products.is_symlink() and products.resolve()==Path.cwd()/products,'Wrong actual Debug products root')
 files=[]
 with os.scandir(products) as entries:
  for index,entry in enumerate(entries):
   require(index<128,'Debug product discovery entry bound')
   if entry.name.endswith('.xctestrun'):
    require(entry.is_file(follow_symlinks=False) and not entry.is_symlink() and len(entry.name.encode())<=512,'Wrong actual xctestrun entry')
    files.append(products/entry.name)
 require(len(files)==1,'Exactly one newly produced xctestrun required')
 from verify_ios_only_release import main as inspect
 return inspect(['build/iOS/Build/Products/Debug-iphonesimulator/QRCatcher.app',
  '--platform','simulator','--configuration','Debug','--xctestrun',str(files[0]),
  '--output','build/ios-first-debug-package.json'])


def retain_prepared():
 # No process call; keep initial-only proof explicit after a device barrier.
 expected=current_identity();require(expected['job']=='platform','Only selected platform receipt retention')
 raw=read_regular(RECEIPT,4096);fingerprint=os.environ.get(INITIAL_HASH_KEY,'')
 require(re.fullmatch('[0-9a-f]{64}',fingerprint) and digest(raw)==fingerprint,'Prepared iOS receipt changed or missing')
 value=json.loads(raw)
 require(type(value) is dict and set(value)==set(expected)|{'tested_tree','source_readback_phase'},'Wrong prepared iOS receipt schema')
 require(all(value[k]==v for k,v in expected.items()) and re.fullmatch('[0-9a-f]{40}',value['tested_tree']),'Foreign source/run/attempt/profile receipt')
 phase='existing bounded managed Mini prepare HEAD/tree/diff' if expected['scope']=='ipad_mini' else 'bounded initial original iOS HEAD/tree/diff/status'
 require(value['source_readback_phase']==phase,'Wrong source-readback phase')
 value['retention_verification']={'initial_receipt_sha256':fingerprint,'device_barrier_observed':blocked(),
  'fresh_source_readback_performed':False,'qualification':'Initial prepare proof only; final managed source/post actions are separate'}
 folder=Path('build/ios-platform-evidence');require(folder.is_dir() and not folder.is_symlink() and folder.resolve()==Path.cwd()/folder,'Wrong owned evidence folder')
 write_json(folder/RECEIPT.name,value,limit=4096);return value


def collect_preflight():
 # Pure bounded retention. No compiler, simulator or host process is started.
 expected=current_identity();require(expected['job']=='preflight','Only original iOS preflight evidence')
 raw=read_regular(RECEIPT,4096);value=json.loads(raw)
 require(digest(raw)==os.environ.get(INITIAL_HASH_KEY) and type(value) is dict and
  set(value)==set(expected)|{'tested_tree','source_readback_phase'} and all(value[k]==v for k,v in expected.items()) and
  re.fullmatch('[0-9a-f]{40}',value['tested_tree']) and value['source_readback_phase']=='bounded initial original iOS HEAD/tree/diff/status','Foreign preflight provenance')
 folder=Path('build/ios-original-preflight-evidence')
 require(not folder.is_symlink() and folder.resolve()==Path.cwd()/folder,'Real preflight evidence directory required')
 folder.mkdir(exist_ok=True)
 require(not any(folder.iterdir()),'Preflight evidence directory must be fresh')
 inventory=[(RECEIPT,4096),(Path('build/ios-original-preflight/summary.json'),64*1024),
  (Path('build/ios-first-debug-package.json'),64*1024),(Path('build/ios-first-release-package.json'),64*1024)]
 inventory += [(Path('build/ios-original-preflight')/(name+'.log'),16*1024) for name in
  ('debug-build','debug-package','release-archive','release-package')]
 files=[];missing=[];used=0
 for path,cap in inventory:
  if not path.exists() and not path.is_symlink():missing.append(str(path));continue
  data=read_regular(path,cap);used+=len(data);require(used<=1000000-64*1024,'Preflight evidence budget exceeded')
  (folder/path.name).write_bytes(data);files.append({'path':str(path),'name':path.name,'bytes':len(data),'sha256':digest(data)})
 result={'version':1,**expected,'tested_tree':value['tested_tree'],'files':files,'missing':missing,
  'evidence_complete':not missing,'observations_qualify_release':False,'initial_source_only':True,
  'owned_process_uncertainty_observed':blocked(),'limit_bytes':1000000}
 write_json(folder/'manifest.json',result,limit=64*1024)
 require(sum(p.stat().st_size for p in folder.iterdir())<=1000000,'Final preflight evidence budget exceeded')
 return result


def main():
 args=sys.argv[1:]
 if args==['render']:
  Path(WORKFLOW).write_text(render_workflow(Path(CANONICAL).read_text()));return
 if args==['validate']:
  record=current_identity();record=write_initial(record,source_readback(record['source_sha']),'bounded initial original iOS HEAD/tree/diff/status')
  print(json.dumps(record,sort_keys=True));return
 if args==['project']:current_identity();print(PROJECT);return
 if args==['debug-package']:return debug_package()
 if args==['collect-preflight']:print(json.dumps(collect_preflight(),sort_keys=True));return
 if len(args)==3 and args[0]=='prepared':print(json.dumps(prepared(*args[1:]),sort_keys=True));return
 raise ValueError('Expected closed original iOS route operation')

if __name__=='__main__':raise SystemExit(main())
