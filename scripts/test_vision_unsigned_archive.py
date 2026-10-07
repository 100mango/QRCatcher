"""Portable Vision archive structure/failure/clock contracts; no native launch."""
import ast,datetime,hashlib,json,os
from pathlib import Path
import plistlib,struct,subprocess,tempfile,unittest,sys,shutil,time
from unittest.mock import patch
import vision_unsigned_archive as m
ROOT=Path(__file__).resolve().parents[1]
CPUS=(0x100000c,0x1000007)
UUIDS={'arm64':'11111111-2222-3333-4444-555555555555','x86_64':'66666666-7777-8888-9999-AAAAAAAAAAAA'}
def thin(cpu,kind=2,platform=1,minimum=0x0d0000):
 cmd=struct.pack('<6I',0x32,24,platform,minimum,0x1b0000,0)
 return struct.pack('<8I',0xfeedfacf,cpu,0,kind,1,len(cmd),0,0)+cmd

def fat(kind=2):
 payloads=[thin(cpu,kind) for cpu in CPUS];offset=8+20*2;table=[]
 for cpu,raw in zip(CPUS,payloads):table.append(struct.pack('>5I',cpu,0,offset,len(raw),0));offset+=len(raw)
 return struct.pack('>2I',0xcafebabe,2)+b''.join(table)+b''.join(payloads)
class Clock:
 def __init__(self,value=100):self.value=value
 def __call__(self):return self.value
 def advance(self,n):self.value+=n

def fixture(root):
 root=root.resolve();a=root/m.ARCHIVE;app=a/m.APP;dwarf=a/m.DWARF
 for p in [app,dwarf.parent]:p.mkdir(parents=True,exist_ok=True)
 meta={'ArchiveVersion':2,'SchemeName':'QRCatcherVision','CreationDate':datetime.datetime(2026,10,7),'ApplicationProperties':{'ApplicationPath':'Applications/QRCatcherVision.app','CFBundleIdentifier':'100mango.QRCatcher','CFBundleShortVersionString':'1.1','CFBundleVersion':'2'}}
 info={'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcherVision','CFBundleName':'QRCatcher','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','MinimumOSVersion':'1.0','CFBundleSupportedPlatforms':['XROS'],'UIDeviceFamily':[7],'DTSDKName':'xros27.0','CFBundleIcons':{'CFBundlePrimaryIcon':'AppIcon'}}
 (a/'Info.plist').write_bytes(plistlib.dumps(meta));(app/'Info.plist').write_bytes(plistlib.dumps(info))
 (a/m.DSYM/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.apple.xcode.dsym.100mango.QRCatcher','CFBundlePackageType':'dSYM','CFBundleVersion':'1.0'}))
 (a/m.EXECUTABLE).write_bytes(thin(CPUS[0],platform=11,minimum=0x10000));dwarf.write_bytes(thin(CPUS[0],kind=10,platform=11,minimum=0x10000))
 source=root/'Shared/FileImportResources/PrivacyInfo.xcprivacy';source.parent.mkdir(parents=True,exist_ok=True)
 privacy=(ROOT/'Shared/FileImportResources/PrivacyInfo.xcprivacy').read_bytes();source.write_bytes(privacy);(app/'PrivacyInfo.xcprivacy').write_bytes(privacy)
 for loc in ['zh-Hans']:
  d=app/f'{loc}.lproj';d.mkdir();src=root/'QRCatcherMac'/f'{loc}.lproj';src.mkdir(parents=True)
  for name in ['Localizable.strings']:
   raw=(ROOT/'QRCatcherMac'/f'{loc}.lproj'/name).read_bytes();(d/name).write_bytes(raw);(src/name).write_bytes(raw)
 (app/'Assets.car').write_bytes(b'compiled native asset container'*5);(app/'PkgInfo').write_bytes(b'APPL????')
 (app/'AppIcon1024x1024.png').write_bytes(b'ordinary generated asset')
 (app/'QR.momd').mkdir();(app/'QR.momd/QR.mom').write_bytes(b'compiled model')
 return a

def uuid_output(a):
 return ''.join(f'UUID: {UUIDS["arm64"]} (arm64) {a/path}\n' for path in [m.EXECUTABLE,m.DWARF]).encode()

def asset_output():
 return json.dumps([{'Name':'AppIcon','RenditionName':'compiler-selected-name','PixelWidth':1024,'PixelHeight':1024,'Scale':1}]).encode()
class ArchiveTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.a=fixture(self.root);self.clock=Clock();self.report={};self.calls=[]
 def tearDown(self):self.temp.cleanup()
 def invoke(self,argv,**kwargs):
  self.calls.append(argv)
  if argv[:3]==['xcrun','dwarfdump','--uuid']:return uuid_output(self.a)
  if argv[:3]==['xcrun','assetutil','--info']:return asset_output()
  if argv[:3]==['xcrun','nm','-u']:return b'                 U _fstat\n'
  raise AssertionError(argv)
 def verify(self):return m.verify_archive(self.a,self.invoke,1000,root=self.root,clock=self.clock,report=self.report)
 def test_vision_archive_and_normal_generated_assets(self):
  proof=self.verify();self.assertEqual(proof['arm64_uuid'],UUIDS['arm64']);self.assertTrue(self.report['archive_inventory']['complete']);self.assertTrue((self.root/'build/archive-inventory.json').exists())
  self.assertEqual(proof['dSYM_version_observations']['CFBundleVersion']['comparison'],'different')
 def test_no_resource_filename_whitelist(self):
  extra=self.a/m.APP/'Standard.Future.Icon-128.png';extra.write_bytes(b'ordinary resource');self.verify();self.assertIn(str(extra.relative_to(self.a)),self.report['archive_inventory']['paths'])
 def test_semantic_failure_retains_complete_structure_and_path(self):
  p=self.a/m.APP/'Info.plist';v=plistlib.loads(p.read_bytes());v['CFBundleIdentifier']='other';p.write_bytes(plistlib.dumps(v))
  with self.assertRaises(m.Rejected):self.verify()
  self.assertTrue(self.report['archive_inventory']['complete']);self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertTrue((self.root/'build/archive-inventory.json').is_file())
 def test_relative_internal_symlink_is_catalogued_without_double_read(self):
  p=self.a/m.APP/'icon-alias';p.symlink_to('AppIcon1024x1024.png');self.verify();row=self.report['archive_inventory']['paths'][str(p.relative_to(self.a))];self.assertEqual(row['type'],'symlink');self.assertEqual(row['target'],'AppIcon1024x1024.png')
 def test_escaping_symlink_retains_bounded_offending_path(self):
  p=self.a/m.APP/'escape';p.symlink_to('/etc/passwd')
  with self.assertRaises(m.Rejected):self.verify()
  self.assertFalse(self.report['archive_inventory']['complete']);self.assertEqual(self.report['archive_inventory']['last_path'],str(p.relative_to(self.a)))
 def test_entry_bound_fails_closed_without_dropping_partial_inventory(self):
  with patch.object(m,'MAX_ENTRIES',2),self.assertRaises(m.Rejected):self.verify()
  self.assertFalse(self.report['archive_inventory']['complete']);self.assertTrue(self.report['archive_inventory']['paths'])
 def test_byte_bound_fails_closed(self):
  with patch.object(m,'MAX_BYTES',1),self.assertRaises(m.Rejected):self.verify()
 def test_inventory_metadata_bound_is_explicit(self):
  with patch.object(m,'MAX_INVENTORY',64),self.assertRaises(m.Rejected):self.verify()
 def test_debug_seam_is_rejected_after_catalogue(self):
  p=self.a/m.EXECUTABLE;p.write_bytes(p.read_bytes()+b'QRCATCHER_TEST_STORE')
  with self.assertRaises(m.Rejected):self.verify()
  self.assertTrue(self.report['archive_inventory']['complete']);self.assertEqual(self.report['offending_path'],m.EXECUTABLE)
 def test_unexpected_test_payload_is_not_a_resource_exception(self):
  p=self.a/m.APP/'PlugIns/Tests.xctest';p.mkdir(parents=True)
  with self.assertRaises(m.Rejected):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)))
 def test_wrong_architecture_fails(self):
  (self.a/m.EXECUTABLE).write_bytes(thin(CPUS[1],platform=11,minimum=0x10000));
  with self.assertRaises(m.Rejected):self.verify()
 def test_nonvision_binary_rejected(self):
  raw=fat().replace(struct.pack('<6I',0x32,24,1,0x0d0000,0x1b0000,0),struct.pack('<6I',0x32,24,2,0x0d0000,0x1b0000,0));(self.a/m.EXECUTABLE).write_bytes(raw)
  with self.assertRaises(m.Rejected):self.verify()
 def test_fake_dwarf_data_not_accepted_by_uuid_text(self):
  (self.a/m.DWARF).write_bytes(fat(2))
  with self.assertRaises(m.Rejected):self.verify()
 def test_unequal_uuids_rejected(self):
  raw=uuid_output(self.a).replace(UUIDS['arm64'].encode(),b'FFFFFFFF-2222-3333-4444-555555555555',1)
  with self.assertRaises(m.Rejected):m.matching_uuid(raw,self.a/m.EXECUTABLE,self.a/m.DWARF)
 def test_privacy_change_identifies_resource(self):
  p=self.a/m.APP/'PrivacyInfo.xcprivacy';p.write_bytes(plistlib.dumps({}))
  with self.assertRaises(m.Rejected):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)))
 def test_distribution_identity_is_not_unsigned_qualification(self):
  p=self.a/'Info.plist';v=plistlib.loads(p.read_bytes());v['ApplicationProperties']['SigningIdentity']='Developer ID';p.write_bytes(plistlib.dumps(v))
  with self.assertRaises(m.Rejected):self.verify()
 def test_dsym_version_missing_or_default_is_observation(self):
  p=self.a/m.DSYM/'Contents/Info.plist';v=plistlib.loads(p.read_bytes());v.pop('CFBundleVersion');p.write_bytes(plistlib.dumps(v));proof=self.verify();self.assertEqual(proof['dSYM_version_observations']['CFBundleVersion']['comparison'],'missing')
 def test_archive_mutation_during_uuid_query_rejected(self):
  old=self.invoke
  def mutate(argv,**kw):
   raw=old(argv,**kw)
   if argv[0]=='xcrun':(self.a/m.APP/'late.bin').write_bytes(b'late')
   return raw
  with self.assertRaises(m.Rejected):m.verify_archive(self.a,mutate,1000,root=self.root,clock=self.clock,report=self.report)
 def test_ancestor_symlink_has_same_canonical_archive_identity(self):
  with tempfile.TemporaryDirectory() as name:
   alias=Path(name).resolve()/'alias';alias.symlink_to(self.root,target_is_directory=True)
   proof=m.verify_archive(alias/m.ARCHIVE,self.invoke,1000,root=alias,clock=self.clock,report=self.report)
   self.assertEqual(proof['arm64_uuid'],UUIDS['arm64'])
 def test_archive_itself_cannot_be_a_symlink(self):
  original=self.a.with_name('actual.xcarchive');self.a.rename(original);self.a.symlink_to(original.name,target_is_directory=True)
  with self.assertRaisesRegex(m.Rejected,'archive-missing-or-linked'):self.verify()
 def test_wrong_archive_path_rejected(self):
  with self.assertRaisesRegex(m.Rejected,'archive-path-mismatch'):
   m.verify_archive(self.a.with_name('other.xcarchive'),self.invoke,1000,root=self.root,clock=self.clock)
 def test_ordinary_icon_assets_directory_is_catalogued(self):
  (self.a/'Assets').mkdir();(self.a/'Assets/ProductIcon.png').write_bytes(b'ordinary generated icon resource')
  self.verify();self.assertIn('Assets/ProductIcon.png',self.report['archive_inventory']['paths'])
 def test_symbolic_required_resource_cannot_qualify(self):
  p=self.a/m.APP/'Info.plist';p.rename(p.with_name('Other.plist'));p.symlink_to('Other.plist')
  with self.assertRaisesRegex(m.Rejected,'required-resource-not-bounded-regular-file'):self.verify()
 def test_hardlink_cannot_hide_duplicate_product(self):
  os.link(self.a/m.EXECUTABLE,self.a/m.APP/'alias.bin')
  with self.assertRaisesRegex(m.Rejected,'archive-hardlink'):self.verify()
 def test_hidden_macho_resource_cannot_qualify(self):
  (self.a/m.APP/'ordinary.data').write_bytes(thin(CPUS[0],platform=11,minimum=0x10000))
  with self.assertRaisesRegex(m.Rejected,'unexpected-mach-o-product'):self.verify()
 def test_signature_directory_cannot_qualify(self):
  (self.a/m.APP/'_CodeSignature').mkdir()
  with self.assertRaisesRegex(m.Rejected,'unexpected-code-test-or-signing-payload'):self.verify()
 def test_populated_signature_command_rejected(self):
  p=self.a/m.EXECUTABLE;raw=bytearray(p.read_bytes());count,size=struct.unpack_from('<II',raw,16)
  struct.pack_into('<II',raw,16,count+1,size+16);raw.extend(struct.pack('<4I',0x1d,16,72,8));raw.extend(b'signhere');p.write_bytes(raw)
  with self.assertRaisesRegex(m.Rejected,'code-signature-load-command-present'):self.verify()
 def test_localization_must_match_source(self):
  (self.a/m.APP/'zh-Hans.lproj/Localizable.strings').write_text('"other" = "value";')
  with self.assertRaisesRegex(m.Rejected,'localization-source-mismatch'):self.verify()
 def test_native_car_decode_is_required(self):
  original=self.invoke
  def run(argv,**kw):return b'[]' if argv[:3]==['xcrun','assetutil','--info'] else original(argv,**kw)
  with self.assertRaisesRegex(m.Rejected,'compiled-asset-inventory-invalid'):
   m.verify_archive(self.a,run,1000,root=self.root,clock=self.clock,report=self.report)
 def test_actual_appicon_metadata_is_required(self):
  p=self.a/m.APP/'Info.plist';info=plistlib.loads(p.read_bytes());info['CFBundleIcons']={};p.write_bytes(plistlib.dumps(info))
  with self.assertRaisesRegex(m.Rejected,'compiled-icon-identity-missing'):self.verify()
 def test_invalid_car_dimensions_rejected_without_guessing_rendition_name(self):
  self.assertFalse(m.compiled_assets(asset_output())['rendered_icon_pixels_qualified'])
  raw=json.loads(asset_output());raw[0]['PixelHeight']=True
  with self.assertRaisesRegex(m.Rejected,'compiled-asset-dimensions-invalid'):m.compiled_assets(json.dumps(raw).encode())
 def test_private_key_path_never_retained_as_ordinary_resource(self):
  (self.a/m.APP/'private.p8').write_bytes(b'not an actual secret')
  with self.assertRaisesRegex(m.Rejected,'signing-input-present'):self.verify()
 def test_pem_key_material_hidden_in_ordinary_resource_is_rejected(self):
  marker=b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----'
  (self.a/m.APP/'ordinary.data').write_bytes(b'prefix'+marker+b'not an actual secret')
  with self.assertRaisesRegex(m.Rejected,'private-key-material-present'):self.verify()
 def test_pem_key_material_split_across_scan_chunks_is_rejected(self):
  marker=b'-----BEGIN '+b'EC PRIVATE KEY-----'
  (self.a/m.APP/'ordinary.data').write_bytes(b'x'*(1024*1024-10)+marker+b'not an actual secret')
  with self.assertRaisesRegex(m.Rejected,'private-key-material-present'):self.verify()
 def test_missing_core_data_model_is_rejected(self):
  (self.a/m.APP/'QR.momd/QR.mom').unlink()
  with self.assertRaisesRegex(m.Rejected,'required-resource-not-bounded-regular-file'):self.verify()
 def test_non_appicon_car_rendition_cannot_qualify(self):
  value=json.loads(asset_output());value[0]['Name']='UnrelatedImage'
  with self.assertRaisesRegex(m.Rejected,'compiled-appicon-rendition-missing'):m.compiled_assets(json.dumps(value).encode())
 def test_missing_file_timestamp_symbol_cannot_qualify(self):
  original=self.invoke
  def run(argv,**kw):return b' U _malloc\n' if argv[:3]==['xcrun','nm','-u'] else original(argv,**kw)
  with self.assertRaisesRegex(m.Rejected,'file-metadata-reader-import-missing'):m.verify_archive(self.a,run,1000,root=self.root,clock=self.clock)
 def test_wrong_release_version_or_build_cannot_qualify(self):
  p=self.a/m.APP/'Info.plist';v=plistlib.loads(p.read_bytes())
  for field in ['CFBundleShortVersionString','CFBundleVersion']:
   changed=dict(v);changed[field]='999';p.write_bytes(plistlib.dumps(changed))
   with self.subTest(field=field),self.assertRaisesRegex(m.Rejected,'application-identity-mismatch'):self.verify()
 def test_generated_vision_icon_identity_and_mutation(self):
  for layer in ['Front','Back']:
   p=self.root/('QRCatcherVision/Assets.xcassets/AppIcon.solidimagestack/'+layer+'.solidimagestacklayer/Content.imageset/Icon.png');p.parent.mkdir(parents=True,exist_ok=True)
   p.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'+struct.pack('>II',1024,1024)+bytes(20))
  value=m.icon_inputs(self.root);self.assertEqual(len(value),2);self.assertTrue(all(row['width']==1024 for row in value.values()))
  p.write_bytes(b'not a valid PNG'+bytes(40))
  with self.assertRaisesRegex(m.Rejected,'generated-icon-dimensions-mismatch'):m.icon_inputs(self.root)
class SourceAndClock(unittest.TestCase):
 def test_pure_macho_functions_match_reviewed_mature_parser(self):
  f=json.loads((ROOT/'scripts/fixtures/vision-archive-inputs.json').read_bytes());raw=(ROOT/'scripts/vision_archive_macho.py').read_text();tree=ast.parse(raw)
  for n in tree.body:
   if isinstance(n,ast.FunctionDef):self.assertEqual(hashlib.sha256(ast.get_source_segment(raw,n).encode()).hexdigest(),f['mature_functions'][n.name])
 def test_all_product_and_guard_inputs_unchanged(self):
  f=json.loads((ROOT/'scripts/fixtures/vision-archive-inputs.json').read_bytes());self.assertEqual(len(f['app_inputs']),52)
  for path,h in f['app_inputs'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),h,path)
 def test_fixed_archive_has_no_signing_launch_or_test(self):
  a=m.ARCHIVE_COMMAND;self.assertEqual(a[-1],'archive');self.assertIn('CODE_SIGNING_ALLOWED=NO',a);self.assertIn('ARCHS=arm64',a);self.assertIn('generic/platform=visionOS',a)
  for bad in ['test','test-without-building','allowProvisioning','exportArchive','codesign']:self.assertFalse(any(bad==x or bad in x.lstrip('-') for x in a if x.startswith('-')),bad)
 def test_workflow_uploads_only_proof_and_is_push_once(self):
  w=(ROOT/m.WORKFLOW).read_text();self.assertIn('path: build/archive-proof/report.json',w);self.assertIn('timeout-minutes: 20',w);self.assertEqual(w.count('runs-on: xcode-27'),1)
  for bad in ['workflow_dispatch','matrix:','retry','*.xcarchive','*.app']:self.assertNotIn(bad,w)
 def test_command_cleanup_has_separate_reserve(self):
  c=Clock();receipts=[]
  def runner(argv,**kw):self.assertEqual(kw['seconds'],20);c.advance(1);return subprocess.CompletedProcess(argv,0,b'ok',b'')
  self.assertEqual(m.command(['safe'],deadline=124,seconds=30,cap=20,receipts=receipts,clock=c,runner=runner,cleanup=2),b'ok');self.assertEqual(receipts[0]['cleanup_reserve_seconds'],4)
 def test_late_return_never_qualifies(self):
  c=Clock()
  def runner(argv,**kw):c.advance(kw['seconds']+1);return subprocess.CompletedProcess(argv,0,b'',b'')
  with self.assertRaises(m.Rejected):m.command(['safe'],deadline=130,seconds=10,cap=20,receipts=[],clock=c,runner=runner)
 def test_unconfirmed_capture_stops_without_followup(self):
  def runner(*a,**k):raise m.CaptureStopped('uncertain',False)
  rows=[]
  with self.assertRaises(m.Rejected):m.command(['safe'],deadline=130,seconds=10,cap=20,receipts=rows,clock=Clock(),runner=runner)
  self.assertEqual(len(rows),1);self.assertFalse(rows[0]['owned_cleanup_confirmed'])
 def test_report_overflow_preserves_bounded_catalogue_and_identity(self):
  report={'schema':1,'qualified':True,'clock':{'report_ready_deadline':200},'source_before':{'GITHUB_SHA':'a'*40},'archive_inventory':{'complete':True,'paths':{'Assets.car':{'bytes':4}}},'commands':['x'*(m.MAX_REPORT+1)]}
  v=json.loads(m.report_bytes(report));self.assertFalse(v['qualified']);self.assertEqual(v['archive_inventory'],report['archive_inventory']);self.assertEqual(v['source_before'],report['source_before'])
 def test_uuid_missing_or_duplicate_slice_rejected(self):
  with self.assertRaises(m.Rejected):m.matching_uuid(b'',Path('app'),Path('dwarf'))
 def test_dwarf_overlap_or_wrong_kind_rejected(self):
  raw=bytearray(fat(10));struct.pack_into('>I',raw,8+20+8,48)
  with self.assertRaises(m.Rejected):m.dwarf_headers(bytes(raw))
  with self.assertRaises(m.Rejected):m.dwarf_headers(thin(CPUS[0],2))
 def test_real_capture_timeout_has_no_followup_command(self):
  receipts=[];started=time.monotonic()
  with self.assertRaisesRegex(m.Rejected,'capture-stopped'):
   m.command([sys.executable,'-c','import time; time.sleep(10)'],deadline=started+5,seconds=.05,cap=64,receipts=receipts)
  self.assertEqual(len(receipts),1);self.assertFalse(receipts[0]['complete']);self.assertTrue(receipts[0]['owned_cleanup_confirmed'])
 def test_real_capture_flood_stops_at_byte_cap(self):
  receipts=[]
  with self.assertRaisesRegex(m.Rejected,'capture-stopped'):
   m.command([sys.executable,'-c','import sys; sys.stdout.write("x"*10000)'],deadline=time.monotonic()+5,seconds=1,cap=32,receipts=receipts)
  self.assertEqual(receipts[0]['reason'],'byte-limit');self.assertTrue(receipts[0]['owned_cleanup_confirmed'])
 def test_historical_evidence_never_becomes_current_ui_execution(self):
  f=json.loads((ROOT/'scripts/fixtures/vision-archive-inputs.json').read_bytes())['functional_evidence_reused']
  self.assertEqual(f['privacy']['source'],m.BASE);self.assertEqual(f['privacy']['workflow_conclusion'],'failure');self.assertFalse(f['privacy']['strict_structured_qualified']);self.assertFalse(f['privacy']['pixels_qualified']);self.assertIn('no UI or hosted test executes',f['scope'])

 def test_workflow_contains_no_signing_keys_credentials_or_paid_runner(self):
  value=(ROOT/m.WORKFLOW).read_text()
  for forbidden in ['secrets.', 'keychain', 'codesign', 'security import', 'large', 'xlarge', 'self-hosted']:
   self.assertNotIn(forbidden,value)
  self.assertIn('contents: read',value);self.assertIn('persist-credentials: false',value)
  self.assertIn('retention-days: 1',value)
  self.assertEqual(m.NEW_PATHS[0],m.WORKFLOW);self.assertEqual(len(m.NEW_PATHS),6)
class SourceIdentity(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()/'source';self.root.mkdir()
  self.fixture=json.loads((ROOT/'scripts/fixtures/vision-archive-inputs.json').read_bytes())
  for path in set(self.fixture['app_inputs'])|set(m.NEW_PATHS):
   dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/path,dest)
  self.env={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+m.WORKFLOW+'@'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
  self.parent=m.BASE;self.diff=['A\t'+p for p in m.NEW_PATHS];self.dirty=''
 def tearDown(self):self.temp.cleanup()
 def git(self,argv,**kwargs):
  mapping={('rev-parse','HEAD'):'a'*40,('rev-parse',m.BASE+'^{tree}'):m.BASE_TREE,('rev-list','--parents','-n','1','HEAD'):'a'*40+' '+self.parent,('status','--porcelain','--untracked-files=all'):self.dirty,('diff','--name-status',m.BASE,'HEAD','--'):'\n'.join(self.diff),('rev-parse','HEAD^{tree}'):'b'*40}
  return mapping[tuple(argv[1:])].encode()
 def test_exact_source_and_ancestor_symlink(self):
  alias=Path(self.temp.name).resolve()/'alias';alias.symlink_to(self.root,target_is_directory=True)
  self.assertEqual(m.source_identity(self.env,self.git,self.root),m.source_identity(self.env,self.git,alias))
 def test_changed_input_is_rejected(self):
  (self.root/'QRCatcherVision/VisionMainView.swift').write_text('changed')
  with self.assertRaisesRegex(m.Rejected,'app-input-changed'):m.source_identity(self.env,self.git,self.root)
 def test_wrong_parent_or_extra_source_diff_is_rejected(self):
  self.parent='c'*40
  with self.assertRaisesRegex(m.Rejected,'source-sole-parent-mismatch'):m.source_identity(self.env,self.git,self.root)
  self.parent=m.BASE;self.diff.append('M\tQRCatcherVision/VisionMainView.swift')
  with self.assertRaisesRegex(m.Rejected,'source-scope-mismatch'):m.source_identity(self.env,self.git,self.root)
 def test_dirty_source_is_rejected(self):
  self.dirty='?? unexpected'
  with self.assertRaisesRegex(m.Rejected,'source-not-clean'):m.source_identity(self.env,self.git,self.root)

class ExecuteAndRetention(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.clock=Clock();self.calls=[];self.fail_archive=False
  self.icon_patch=patch.object(m,'icon_inputs',return_value={'synthetic':'portable-test-only'});self.icon_patch.start();self.addCleanup(self.icon_patch.stop)
  self.identity={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+m.WORKFLOW+'@'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
 def tearDown(self):self.temp.cleanup()
 def runner(self,argv,**kwargs):
  self.calls.append(argv);raw=b'';code=0
  if argv==['xcodebuild','-version']:raw=b'Xcode 27.0\nBuild version 27A266a\n'
  elif argv==['xcodebuild','-showsdks']:raw=b'xros27.0\n'
  elif argv==['sw_vers']:raw=b'ProductVersion: 27.0\nBuildVersion: 26A428\n'
  elif argv==m.ARCHIVE_COMMAND:
   if self.fail_archive:code=65;raw=b'Archive failed, bounded compiler details'
   else:fixture(self.root)
  elif argv[:3]==['xcrun','dwarfdump','--uuid']:raw=uuid_output(self.root/m.ARCHIVE)
  elif argv[:3]==['xcrun','assetutil','--info']:raw=asset_output()
  elif argv[:3]==['xcrun','nm','-u']:raw=b'                 U _fstat\n'
  self.clock.advance(.1);return subprocess.CompletedProcess(argv,code,raw,b'')
 def execute(self):
  with patch.object(m,'source_identity',return_value=dict(self.identity)):
   return m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
 def test_full_fixed_pipeline_qualifies_proof_only(self):
  r=self.execute();self.assertTrue(r['qualified'],r.get('failure'));self.assertFalse(r['binary_handoff']);self.assertFalse(r['signing_qualified']);self.assertFalse(r['store_qualified']);self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';marker.write_text('');decoded=m.retain_report(r,output,marker,clock=self.clock)
  self.assertTrue(decoded['qualified']);self.assertTrue(decoded['archive_inventory']['complete']);self.assertEqual(set(x.name for x in output.iterdir()),{'report.json'});self.assertEqual(marker.read_text(),'evidence_ready=true\n')
 def test_archive_failure_keeps_native_diagnostic_and_never_proves_or_retries(self):
  self.fail_archive=True;r=self.execute();self.assertFalse(r['qualified']);self.assertEqual(r['failure']['phase'],'archive');self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertIn('bounded compiler details',r['commands'][-1]['stdout']);self.assertNotIn('proof',r)
 def test_source_failure_starts_no_command(self):
  with patch.object(m,'source_identity',side_effect=m.Rejected('source mismatch')):r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
  self.assertFalse(r['qualified']);self.assertEqual(self.calls,[])
 def test_archive_capture_timeout_is_terminal_even_with_host_cleanup(self):
  original=self.runner
  def runner(argv,**kw):
   if argv==m.ARCHIVE_COMMAND:self.calls.append(argv);raise m.CaptureStopped('duration-limit',True)
   return original(argv,**kw)
  with patch.object(m,'source_identity',return_value=dict(self.identity)):
   r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=runner)
  self.assertFalse(r['qualified']);self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND);self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertNotIn('archive_inventory',r)
 def test_error_text_with_zero_status_still_fails(self):
  original=self.runner
  def runner(argv,**kw):
   value=original(argv,**kw)
   return subprocess.CompletedProcess(argv,0,b'error: rejected archive',b'') if argv==m.ARCHIVE_COMMAND else value
  with patch.object(m,'source_identity',return_value=dict(self.identity)):
   r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=runner)
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['reason'],'archive-reported-error');self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
 def test_generated_project_change_stops_before_archive(self):
  with patch.object(m,'source_identity',side_effect=[dict(self.identity),dict(self.identity,changed=True)]):
   r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
  self.assertFalse(r['qualified']);self.assertNotIn(m.ARCHIVE_COMMAND,self.calls)
 def test_no_simulator_or_hosted_action_in_entire_driver(self):
  r=self.execute();self.assertTrue(r['qualified'])
  self.assertFalse(any('simctl' in call or 'test-without-building' in call or 'build-for-testing' in call for call in self.calls))
  self.assertEqual([call for call in self.calls if call[0]=='xcodebuild' and 'archive' in call],[m.ARCHIVE_COMMAND])
 def test_late_report_cannot_emit_upload_marker(self):
  r=self.execute();r['clock']['report_ready_deadline']=self.clock();marker=self.root/'output';marker.write_text('prior\n')
  result=m.retain_report(r,self.root/'build/proof',marker,clock=self.clock);self.assertFalse(result['qualified']);self.assertEqual(marker.read_text(),'prior\n')
 def test_full_upload_reserve_is_required_and_failed_action_stays_failed(self):
  r=self.execute();r['upload_observation']=m.admit_upload(r,clock=self.clock)
  self.assertFalse(m.finish_upload(r,'failure',clock=self.clock)['upload_qualified']);self.assertTrue(m.finish_upload(r,'success',clock=self.clock)['upload_qualified'])
  self.clock.value=r['clock']['started_monotonic']+m.PHASE_END['evidence']-59
  with self.assertRaises(m.Rejected):m.admit_upload(r,clock=self.clock)
 def test_late_upload_does_not_reset_deadline(self):
  r=self.execute();r['upload_observation']=m.admit_upload(r,clock=self.clock);self.clock.advance(61);self.assertFalse(m.finish_upload(r,'success',clock=self.clock)['upload_qualified'])
 def test_retry_and_dispatch_identity_rejected(self):
  self.assertEqual(m.environment(self.identity),self.identity)
  for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main')]:
   with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(self.identity|{key:value})

 def test_icon_materialization_failure_never_archives(self):
  original=self.runner
  def runner(argv,**kw):
   if argv==['xcrun','swift','scripts/materialize_native_icons.swift']:
    self.calls.append(argv);return subprocess.CompletedProcess(argv,1,b'bounded failure',b'')
   return original(argv,**kw)
  with patch.object(m,'source_identity',return_value=dict(self.identity)):
   r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=runner)
  self.assertFalse(r['qualified']);self.assertNotIn(m.ARCHIVE_COMMAND,self.calls)
 def test_generated_icon_mutation_prevents_final_qualification(self):
  with patch.object(m,'source_identity',return_value=dict(self.identity)),patch.object(m,'icon_inputs',side_effect=[{'before':'same'},{'after':'different'}]):
   r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['reason'],'generated-icon-input-changed')

if __name__=='__main__':unittest.main()
