"""Portable Mac archive structure/failure/clock contracts; no native launch."""
import ast,datetime,hashlib,json,os
from pathlib import Path
import plistlib,struct,subprocess,sys,tempfile,unittest
from unittest.mock import patch
import mac_unsigned_archive as m
ROOT=Path(__file__).resolve().parents[1]
CPUS=(0x100000c,0x1000007)
UUIDS={'arm64':'11111111-2222-3333-4444-555555555555','x86_64':'66666666-7777-8888-9999-AAAAAAAAAAAA'}
def thin(cpu,kind=2,platform=1,minimum=0x0d0000,sdk=0x1b0000):
 cmd=struct.pack('<6I',0x32,24,platform,minimum,sdk,0)
 return struct.pack('<8I',0xfeedfacf,cpu,0,kind,1,len(cmd),0,0)+cmd

def fat(kind=2,payloads=None):
 payloads=[thin(cpu,kind) for cpu in CPUS] if payloads is None else payloads;offset=8+20*2;table=[]
 for cpu,raw in zip(CPUS,payloads):table.append(struct.pack('>5I',cpu,0,offset,len(raw),0));offset+=len(raw)
 return struct.pack('>2I',0xcafebabe,2)+b''.join(table)+b''.join(payloads)
class Clock:
 def __init__(self,value=100):self.value=value
 def __call__(self):return self.value
 def advance(self,n):self.value+=n

def fixture(root):
 a=root/m.ARCHIVE;app=a/m.APP;dwarf=a/m.DWARF
 for p in [app/'Contents/MacOS',app/'Contents/Resources',dwarf.parent]:p.mkdir(parents=True,exist_ok=True)
 meta={'ArchiveVersion':2,'SchemeName':'QRCatcherMac','CreationDate':datetime.datetime(2026,10,7),'ApplicationProperties':{'ApplicationPath':'Applications/QRCatcherMac.app','CFBundleIdentifier':'100mango.QRCatcher','CFBundleShortVersionString':'1.1','CFBundleVersion':'2'}}
 info={'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcherMac','CFBundleName':'QRCatcher','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','LSMinimumSystemVersion':'13.0','CFBundleIconFile':'AppIcon','NSCameraUsageDescription':'Read a QR code using a camera you choose. Images are processed locally.'}
 (a/'Info.plist').write_bytes(plistlib.dumps(meta));(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
 (a/m.DSYM/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.apple.xcode.dsym.100mango.QRCatcher','CFBundlePackageType':'dSYM','CFBundleVersion':'1.0'}))
 (a/m.EXECUTABLE).write_bytes(fat());dwarf.write_bytes(fat(10))
 source=root/'Shared/FileImportResources/PrivacyInfo.xcprivacy';source.parent.mkdir(parents=True,exist_ok=True)
 privacy=(ROOT/'Shared/FileImportResources/PrivacyInfo.xcprivacy').read_bytes();source.write_bytes(privacy);(app/'Contents/Resources/PrivacyInfo.xcprivacy').write_bytes(privacy)
 d=app/'Contents/Resources/zh-Hans.lproj';d.mkdir()
 source_locale=root/'QRCatcherMac/zh-Hans.lproj';source_locale.mkdir(parents=True,exist_ok=True)
 for name in ['Localizable.strings','InfoPlist.strings']:
  raw=(ROOT/'QRCatcherMac/zh-Hans.lproj'/name).read_bytes();(source_locale/name).write_bytes(raw)
  (d/name).write_bytes(plistlib.dumps(m.package.strings_dictionary(raw),fmt=plistlib.FMT_BINARY))
 for name in ['Assets.car','AppIcon.icns','AppIcon512x512@2x.png']:(app/'Contents/Resources'/name).write_bytes(b'normal generated asset')
 model=app/'Contents/Resources/QR.momd/QR.mom';model.parent.mkdir();model.write_bytes(b'portable compiled-model placeholder')
 (app/'Contents/PkgInfo').write_bytes(b'APPL????')
 return a

def uuid_output(a):
 return ''.join(f'UUID: {UUIDS[arch]} ({arch}) {a/path}\n' for path in [m.EXECUTABLE,m.DWARF] for arch in ['arm64','x86_64']).encode()

def native_output(argv,a):
 """Strict boundary mocks: portable fixtures never invoke any Apple tool."""
 if argv==['xcrun','dwarfdump','--uuid',str(a/m.EXECUTABLE),str(a/m.DWARF)]:return uuid_output(a)
 if argv==['xcrun','nm','-u',str(a/m.EXECUTABLE)]:return b'                 U _fstat\n'
 icon=a/m.APP/'Contents/Resources/AppIcon.icns'
 if argv==['xcrun','swift','scripts/verify_mac_icon.swift',str(icon),'build/icon-verification/mac-bundled-icon.png']:
  return json.dumps({'icns_sha256':hashlib.sha256(icon.read_bytes()).hexdigest(),'decoded_sizes':[[1024,1024],[512,512]],'largest_size':[1024,1024]}).encode()
 raise AssertionError('Unmocked native boundary: '+repr(argv))

class PortableTestCase(unittest.TestCase):
 def setUp(self):
  wall=patch.object(m.time,'time',return_value=datetime.datetime.fromisoformat(m.WINDOW_START).timestamp()+1)
  wall.start();self.addCleanup(wall.stop)
  guard=patch.object(subprocess,'Popen',side_effect=AssertionError('Portable archive tests must not spawn a process'))
  guard.start();self.addCleanup(guard.stop)

class ArchiveTests(PortableTestCase):
 def setUp(self):super().setUp();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.a=fixture(self.root);self.clock=Clock();self.report={};self.calls=[]
 def tearDown(self):self.temp.cleanup()
 def invoke(self,argv,**kwargs):
  self.calls.append(argv)
  return native_output(argv,self.a)
 def verify(self):return m.verify_archive(self.a,self.invoke,1000,root=self.root,clock=self.clock,report=self.report)
 def test_universal_archive_and_normal_generated_assets(self):
  proof=self.verify();self.assertEqual(set(proof['uuids']),{'arm64','x86_64'});self.assertTrue(self.report['archive_inventory']['complete']);self.assertTrue((self.root/'build/archive-inventory.json').exists())
  self.assertEqual(proof['dSYM_version_observations']['CFBundleVersion']['comparison'],'different')
  self.assertEqual(proof['application_metadata']['CFBundleName'],'QRCatcher');self.assertEqual(proof['actual_file_metadata_imports'],['_fstat'])
  self.assertFalse((self.a/m.APP/'Contents/Resources/en.lproj').exists());self.assertEqual(len(self.calls),3)
 def test_no_resource_filename_whitelist(self):
  extra=self.a/m.APP/'Contents/Resources/Standard.Future.Icon-128.png';extra.write_bytes(b'ordinary resource');self.verify();self.assertIn(str(extra.relative_to(self.a)),self.report['archive_inventory']['paths'])
 def test_semantic_failure_retains_complete_structure_and_path(self):
  p=self.a/m.APP/'Contents/Info.plist';v=plistlib.loads(p.read_bytes());v['CFBundleIdentifier']='other';p.write_bytes(plistlib.dumps(v))
  with self.assertRaises(m.Rejected):self.verify()
  self.assertTrue(self.report['archive_inventory']['complete']);self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertTrue((self.root/'build/archive-inventory.json').is_file())
 def test_metadata_read_error_keeps_other_plist_observations(self):
  p=self.a/'Info.plist';p.write_bytes(b'not a plist')
  with self.assertRaises(plistlib.InvalidFileException):self.verify()
  rows=self.report['archive_metadata_diagnostics'];self.assertEqual(len(rows),3)
  self.assertEqual(rows['Info.plist']['read_error']['type'],'InvalidFileException')
  self.assertEqual(rows[m.APP+'/Contents/Info.plist']['metadata']['CFBundleVersion'],'2')
  self.assertEqual(rows[m.DSYM+'/Contents/Info.plist']['metadata']['CFBundlePackageType'],'dSYM')
  self.assertEqual(self.report['current_proof_path'],'Info.plist');self.assertEqual(self.calls,[])
 def test_relative_internal_symlink_is_catalogued_without_double_read(self):
  p=self.a/m.APP/'Contents/Resources/icon-alias';p.symlink_to('AppIcon.icns');self.verify();row=self.report['archive_inventory']['paths'][str(p.relative_to(self.a))];self.assertEqual(row['type'],'symlink');self.assertEqual(row['target'],'AppIcon.icns')
 def test_escaping_symlink_retains_bounded_offending_path(self):
  p=self.a/m.APP/'Contents/Resources/escape';p.symlink_to('/etc/passwd')
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
  p=self.a/m.EXECUTABLE;p.write_bytes(p.read_bytes()+b'QRCATCHER_MAC_PUBLIC_METADATA_')
  with self.assertRaises(m.Rejected):self.verify()
  self.assertTrue(self.report['archive_inventory']['complete']);self.assertEqual(self.report['offending_path'],m.EXECUTABLE)
 def test_unexpected_test_payload_is_not_a_resource_exception(self):
  p=self.a/m.APP/'Contents/PlugIns/Tests.xctest';p.mkdir(parents=True)
  with self.assertRaises(m.Rejected):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)))
  self.assertEqual(len(self.report['archive_metadata_diagnostics']),3)
 def test_single_architecture_fails(self):
  (self.a/m.EXECUTABLE).write_bytes(thin(CPUS[0]));
  with self.assertRaises(m.Rejected):self.verify()
 def test_nonmac_binary_rejected(self):
  raw=fat().replace(struct.pack('<6I',0x32,24,1,0x0d0000,0x1b0000,0),struct.pack('<6I',0x32,24,2,0x0d0000,0x1b0000,0));(self.a/m.EXECUTABLE).write_bytes(raw)
  with self.assertRaises(m.Rejected):self.verify()
 def test_wrong_version_in_one_slice_is_rejected(self):
  for overrides in ({'platform':2},{'minimum':0x0e0000},{'sdk':0x1a0000}):
   with self.subTest(overrides=overrides):
    (self.a/m.EXECUTABLE).write_bytes(fat(payloads=[thin(CPUS[0]),thin(CPUS[1],**overrides)]))
    with self.assertRaisesRegex(m.Rejected,'binary-platform-version-mismatch'):self.verify()
    self.assertEqual(self.calls,[])
 def test_wrong_model_name_is_rejected(self):
  p=self.a/m.APP/'Contents/Resources/QR.momd/QR.mom';p.rename(p.with_name('Wrong.mom'))
  with self.assertRaisesRegex(m.Rejected,'required-compiled-resource-missing'):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertEqual(self.calls,[])
 def test_standalone_model_does_not_replace_model_bundle(self):
  p=self.a/m.APP/'Contents/Resources/QR.momd/QR.mom';p.rename(p.parent.parent/'QR.mom');p.parent.rmdir()
  with self.assertRaisesRegex(m.Rejected,'required-compiled-resource-missing'):self.verify()
  self.assertEqual(self.calls,[])
 def test_both_chinese_tables_are_required(self):
  for name in ('Localizable.strings','InfoPlist.strings'):
   with self.subTest(name=name):
    p=self.a/m.APP/'Contents/Resources/zh-Hans.lproj'/name;raw=p.read_bytes();p.unlink()
    with self.assertRaisesRegex(m.Rejected,'localized-resource-missing-or-oversized'):self.verify()
    self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertEqual(self.calls,[]);p.write_bytes(raw)
 def test_oversized_chinese_table_is_rejected_before_parsing(self):
  p=self.a/m.APP/'Contents/Resources/zh-Hans.lproj/Localizable.strings';p.write_bytes(b' '*(64*1024+1))
  with patch.object(m.package,'strings_dictionary',side_effect=AssertionError('Oversized strings must not be parsed')):
   with self.assertRaisesRegex(m.Rejected,'localized-resource-missing-or-oversized'):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertEqual(self.calls,[]);self.assertTrue(self.report['archive_inventory']['complete'])
 def test_compiled_chinese_table_must_equal_source_dictionary(self):
  p=self.a/m.APP/'Contents/Resources/zh-Hans.lproj/InfoPlist.strings';values=plistlib.loads(p.read_bytes());values['CFBundleDisplayName']='Wrong product';p.write_bytes(plistlib.dumps(values))
  with self.assertRaisesRegex(m.Rejected,'localized-resource-source-mismatch'):self.verify()
  self.assertEqual(self.report['offending_path'],str(p.relative_to(self.a)));self.assertEqual(self.calls,[])
 def test_missing_file_metadata_import_stops_before_icon_and_uuid(self):
  def invoke(argv,**kwargs):self.calls.append(argv);return b' U _not_fstat\n'
  with self.assertRaisesRegex(m.Rejected,'file-metadata-reader-import-missing'):m.verify_archive(self.a,invoke,1000,root=self.root,clock=self.clock,report=self.report)
  self.assertEqual(self.calls,[['xcrun','nm','-u',str(self.a/m.EXECUTABLE)]])
 def test_icon_hash_mismatch_stops_before_uuid(self):
  def invoke(argv,**kwargs):
   self.calls.append(argv)
   return json.dumps({'icns_sha256':'0'*64}).encode() if argv[:2]==['xcrun','swift'] else native_output(argv,self.a)
  with self.assertRaisesRegex(m.Rejected,'compiled-icon-observation-mismatch'):m.verify_archive(self.a,invoke,1000,root=self.root,clock=self.clock,report=self.report)
  self.assertEqual(len(self.calls),2);self.assertFalse(any('dwarfdump' in a for a in self.calls))
 def test_native_proof_boundaries_keep_fixed_budgets(self):
  observations=[]
  def invoke(argv,**kwargs):observations.append((argv,kwargs));return native_output(argv,self.a)
  m.verify_archive(self.a,invoke,1000,root=self.root,clock=self.clock,report=self.report)
  self.assertEqual([x[0][1] for x in observations],['nm','swift','dwarfdump'])
  self.assertEqual([x[1] for x in observations],[{'seconds':15,'cap':256*1024},{'seconds':45,'cap':16384,'cleanup':10},{'seconds':10,'cap':8192,'cleanup':10}])
 def test_fake_dwarf_data_not_accepted_by_uuid_text(self):
  (self.a/m.DWARF).write_bytes(fat(2))
  with self.assertRaises(m.Rejected):self.verify()
 def test_unequal_uuids_rejected(self):
  raw=uuid_output(self.a).replace(UUIDS['arm64'].encode(),b'FFFFFFFF-2222-3333-4444-555555555555',1)
  with self.assertRaises(m.Rejected):m.matching_uuid(raw,self.a/m.EXECUTABLE,self.a/m.DWARF)
 def test_privacy_change_identifies_resource(self):
  p=self.a/m.APP/'Contents/Resources/PrivacyInfo.xcprivacy';p.write_bytes(plistlib.dumps({}))
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
   if argv[:3]==['xcrun','dwarfdump','--uuid']:(self.a/m.APP/'Contents/Resources/late.bin').write_bytes(b'late')
   return raw
  with self.assertRaises(m.Rejected):m.verify_archive(self.a,mutate,1000,root=self.root,clock=self.clock,report=self.report)
class SourceAndClock(PortableTestCase):
 def test_pure_macho_functions_match_reviewed_mature_parser(self):
  f=json.loads((ROOT/'scripts/fixtures/mac-archive-inputs.json').read_bytes());raw=(ROOT/'scripts/mac_archive_macho.py').read_text();tree=ast.parse(raw)
  for n in tree.body:
   if isinstance(n,ast.FunctionDef):self.assertEqual(hashlib.sha256(ast.get_source_segment(raw,n).encode()).hexdigest(),f['mature_functions'][n.name])
 def test_product_and_support_input_closure_unchanged(self):
  f=json.loads((ROOT/'scripts/fixtures/mac-archive-inputs.json').read_bytes());self.assertEqual(f['product_input_count'],38);self.assertEqual(f['source_only_support_count'],8);self.assertEqual(len(f['app_inputs']),46)
  for path,h in f['app_inputs'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),h,path)
  self.assertEqual(hashlib.sha256((ROOT/'scripts/mac_archive_capture.py').read_bytes()).hexdigest(),f['collector_sha256'])
 def test_fixed_archive_has_no_signing_launch_or_test(self):
  a=m.ARCHIVE_COMMAND;self.assertEqual(a[-1],'archive');self.assertIn('CODE_SIGNING_ALLOWED=NO',a);self.assertIn('ARCHS=arm64 x86_64',a);self.assertIn('generic/platform=macOS',a)
  self.assertEqual(a[a.index('-project')+1],'QRCatcher.xcodeproj');self.assertEqual(a[a.index('-scheme')+1],'QRCatcherMac')
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
  report={'schema':1,'qualified':True,'clock':{'report_ready_deadline':200},'source_before':{'GITHUB_SHA':'a'*40},'archive_inventory':{'complete':True,'paths':{'Assets.car':{'bytes':4}}},'archive_metadata_diagnostics':{'Info.plist':{'read_error':{'type':'InvalidFileException','reason':'Invalid file'}}},'commands':['x'*(m.MAX_REPORT+1)]}
  v=json.loads(m.report_bytes(report));self.assertFalse(v['qualified']);self.assertEqual(v['archive_inventory'],report['archive_inventory']);self.assertEqual(v['source_before'],report['source_before']);self.assertEqual(v['archive_metadata_diagnostics'],report['archive_metadata_diagnostics'])
 def test_uuid_missing_or_duplicate_slice_rejected(self):
  with self.assertRaises(m.Rejected):m.matching_uuid(b'',Path('app'),Path('dwarf'))
 def test_dwarf_overlap_or_wrong_kind_rejected(self):
  raw=bytearray(fat(10));struct.pack_into('>I',raw,8+20+8,48)
  with self.assertRaises(m.Rejected):m.dwarf_headers(bytes(raw))
  with self.assertRaises(m.Rejected):m.dwarf_headers(thin(CPUS[0],2))

class ExecuteAndRetention(PortableTestCase):
 def setUp(self):
  super().setUp()
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.clock=Clock();self.calls=[];self.fail_archive=False
  self.identity={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+m.WORKFLOW+'@'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_NUMBER':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
 def tearDown(self):self.temp.cleanup()
 def runner(self,argv,**kwargs):
  self.calls.append(argv);raw=b'';code=0
  if argv==['xcodebuild','-version']:raw=b'Xcode 27.0\nBuild version 27A266a\n'
  elif argv==['xcodebuild','-showsdks']:raw=b'macosx27.0\n'
  elif argv==['sw_vers']:raw=b'ProductVersion: 27.0\nBuildVersion: 26A428\n'
  elif argv==m.ARCHIVE_COMMAND:
   if self.fail_archive:code=65;raw=b'Archive failed, bounded compiler details'
   else:fixture(self.root);raw=b'** ARCHIVE SUCCEEDED **\n'
  elif argv[0]=='xcrun':raw=native_output(argv,self.root/m.ARCHIVE)
  elif argv in ([sys.executable,'scripts/materialize_mac_icons.py'],*[ [sys.executable,*optimize,'-m','unittest','discover','-s','scripts','-p','test_mac_unsigned_archive.py'] for optimize in ([],['-O']) ]):pass
  else:raise AssertionError('Unmocked pipeline boundary: '+repr(argv))
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
  self.assertIn('bounded compiler details',r['commands'][-1]['stdout']);self.assertNotIn('proof',r);self.assertNotIn('archive_inventory',r)
 def archive_reported_error(self,*,stderr=False,create_archive=True):
  original=self.runner
  def runner(argv,**kwargs):
   if argv!=m.ARCHIVE_COMMAND:return original(argv,**kwargs)
   self.calls.append(argv)
   if create_archive:fixture(self.root)
   self.clock.advance(.1);error=b'error: archive exporter reported a bounded failure\n'
   return subprocess.CompletedProcess(argv,0,b'** ARCHIVE SUCCEEDED **\n'+(b'' if stderr else error),error if stderr else b'')
  with patch.object(self,'runner',side_effect=runner):r=self.execute()
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['phase'],'archive');self.assertEqual(r['failure']['reason'],'archive-reported-error')
  self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1);self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertNotIn('proof',r);self.assertNotIn('source_after',r);self.assertTrue(r['commands'][-1]['complete']);self.assertEqual(r['commands'][-1]['returncode'],0)
  self.assertEqual(r['archive_file_observation_scope'],'after-known-zero-exit-with-error; pure files only')
  return r
 def test_zero_exit_stdout_error_keeps_files_without_second_native_call(self):
  r=self.archive_reported_error();self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(len(r['archive_metadata_diagnostics']),3)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';retained=m.retain_report(r,output,marker,clock=self.clock)
  self.assertFalse(retained['qualified']);self.assertTrue(retained['archive_inventory']['complete']);self.assertEqual(len(retained['archive_metadata_diagnostics']),3)
  self.assertEqual(set(x.name for x in output.iterdir()),{'report.json'})
 def test_zero_exit_stderr_error_keeps_files_without_second_native_call(self):
  r=self.archive_reported_error(stderr=True);self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(len(r['archive_metadata_diagnostics']),3)
 def test_zero_exit_error_without_archive_keeps_original_failure(self):
  r=self.archive_reported_error(create_archive=False);self.assertEqual(r['archive_file_observation_error']['type'],'FileNotFoundError');self.assertFalse(r['archive_inventory']['complete'])
 def test_unconfirmed_archive_exit_starts_no_file_or_native_proof(self):
  original=self.runner
  def runner(argv,**kwargs):
   if argv!=m.ARCHIVE_COMMAND:return original(argv,**kwargs)
   self.calls.append(argv);fixture(self.root)
   error=m.CaptureStopped('descendant-exit-unconfirmed',False);error.stdout_prefix=b'error: retained uncertain archive';error.stderr_capture=b'bounded stderr';raise error
  with patch.object(self,'runner',side_effect=runner):r=self.execute()
  self.assertFalse(r['qualified']);self.assertEqual(r['failure']['reason'],'capture-stopped');self.assertEqual(self.calls[-1],m.ARCHIVE_COMMAND)
  self.assertNotIn('proof',r);self.assertNotIn('archive_inventory',r);self.assertNotIn('archive_file_observation_scope',r)
  self.assertFalse(r['commands'][-1]['owned_cleanup_confirmed']);self.assertIn('retained uncertain archive',r['commands'][-1]['stdout'])
 def check_metadata_failure(self,path,key,value,reason):
  original=self.runner
  def mutate(argv,**kwargs):
   result=original(argv,**kwargs)
   if argv==m.ARCHIVE_COMMAND:
    p=self.root/m.ARCHIVE/path;v=plistlib.loads(p.read_bytes());v[key]=value;p.write_bytes(plistlib.dumps(v))
   return result
  with patch.object(self,'runner',side_effect=mutate):r=self.execute()
  self.assertFalse(r['qualified']);self.assertNotIn('proof',r);self.assertEqual(r['failure']['phase'],'proof');self.assertIn(reason,r['failure']['reason']);self.assertEqual(r['failure']['offending_path'],path)
  self.assertTrue(r['archive_inventory']['complete']);self.assertEqual(self.calls.count(m.ARCHIVE_COMMAND),1)
  rows=r['archive_metadata_diagnostics'];self.assertEqual(set(rows),{'Info.plist',m.APP+'/Contents/Info.plist',m.DSYM+'/Contents/Info.plist'})
  for name,row in rows.items():self.assertEqual(row['metadata'],plistlib.loads((self.root/m.ARCHIVE/name).read_bytes()))
  self.assertEqual(rows[path]['metadata'][key],value)
  output=self.root/'build/archive-proof';marker=self.root/'step-output';marker.write_text('')
  retained=m.retain_report(r,output,marker,clock=self.clock);self.assertEqual(retained['archive_metadata_diagnostics'][path]['metadata'][key],value)
  overflow=json.loads(m.report_bytes(r|{'commands':['x'*(m.MAX_REPORT+1)]}))
  self.assertEqual(overflow['archive_metadata_diagnostics'],retained['archive_metadata_diagnostics']);self.assertEqual(overflow['failure']['original_failure'],r['failure']);self.assertFalse(overflow['qualified'])
 def test_archive_version_failure_retains_all_three_plists(self):
  self.check_metadata_failure('Info.plist','ArchiveVersion',999,'archive-metadata-mismatch')
 def test_application_version_failure_retains_all_three_plists(self):
  self.check_metadata_failure(m.APP+'/Contents/Info.plist','CFBundleVersion','unexpected-build','application-identity-mismatch')
 def test_dsym_identity_failure_retains_all_three_plists(self):
  self.check_metadata_failure(m.DSYM+'/Contents/Info.plist','CFBundleIdentifier','unexpected.dsym','dSYM-metadata-mismatch')
 def test_source_failure_starts_no_command(self):
  with patch.object(m,'source_identity',side_effect=m.Rejected('source mismatch')):r=m.execute(env=self.identity,root=self.root,clock=self.clock,runner=self.runner)
  self.assertFalse(r['qualified']);self.assertEqual(self.calls,[])
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
  for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_NUMBER','2'),('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main')]:
   with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(self.identity|{key:value})

class ModelMetadataDiagnostic(PortableTestCase):
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.a=fixture(self.root);self.clock=Clock();self.report={}
  self.path=self.a/m.MODEL_VERSION_INFO
 def write(self,value,fmt=plistlib.FMT_BINARY):
  raw=plistlib.dumps(value,fmt=fmt);self.path.write_bytes(raw);return raw
 def observe(self):
  return m.observe_archive_files(self.a,1000,root=self.root,clock=self.clock,report=self.report)
 def test_exact_binary_bytes_hash_decoded_data_and_inventory(self):
  value={'NSManagedObjectModel_CurrentVersionName':'QR','NSManagedObjectModel_VersionHashes':{'QR':{'URLEntity':b'\x00\xff\x10'}},'Date':datetime.datetime(2026,10,15)}
  raw=self.write(value);self.observe();r=self.report['core_data_metadata_diagnostic']
  self.assertTrue(r['complete']);self.assertEqual(bytes.fromhex(r['raw_hex']),raw);self.assertEqual(r['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(r['bytes'],len(raw))
  self.assertEqual(r['metadata']['NSManagedObjectModel_VersionHashes']['QR']['URLEntity'],{'plist_data_hex':'00ff10'})
  self.assertEqual(r['metadata']['Date'],{'plist_date':'2026-10-15T00:00:00'})
  self.assertEqual(r['comparison'],'matches-private-validator');self.assertEqual(r['compiled_model_files'],[m.MODEL_ROOT+'/QR.mom'])
  self.assertIn(m.MODEL_VERSION_INFO,self.report['core_data_resource_observation'])
  retained=json.loads(m.report_bytes(self.report));self.assertEqual(retained['core_data_metadata_diagnostic'],r)
 def test_xml_metadata_exact_bytes(self):
  raw=self.write({'NSManagedObjectModel_CurrentVersionName':'QR'},plistlib.FMT_XML);self.observe()
  self.assertEqual(bytes.fromhex(self.report['core_data_metadata_diagnostic']['raw_hex']),raw)
 def test_missing_optional_version_info_is_an_explicit_observation(self):
  self.observe();r=self.report['core_data_metadata_diagnostic'];self.assertTrue(r['complete']);self.assertFalse(r['present']);self.assertEqual(r['comparison'],'VersionInfo.plist-missing');self.assertNotIn('metadata',r)
 def test_missing_current_version_key_is_not_invented(self):
  self.write({'NSManagedObjectModel_VersionHashes':{'QR':{'URLEntity':b'\xff'}}});self.observe();r=self.report['core_data_metadata_diagnostic']
  self.assertEqual(r['comparison'],'current-version-key-missing');self.assertFalse(r['current_version_key_present']);self.assertNotIn('NSManagedObjectModel_CurrentVersionName',r['metadata'])
 def test_other_version_and_type_preserved_not_coerced_or_qualified(self):
  for value in ['Other',7,b'QR',False]:
   with self.subTest(value=value):
    self.write({'NSManagedObjectModel_CurrentVersionName':value});self.observe();r=self.report['core_data_metadata_diagnostic'];self.assertEqual(r['comparison'],'differs-from-private-validator');self.assertTrue(r['observation_only']);self.assertNotIn('release_qualified',r)
 def test_observation_does_not_rewrite_existing_semantic_contract(self):
  self.write({'NSManagedObjectModel_CurrentVersionName':'Other'})
  proof=m.verify_archive(self.a,lambda argv,**kw:native_output(argv,self.a),1000,root=self.root,clock=self.clock,report=self.report)
  self.assertEqual(proof['application_metadata']['CFBundleIdentifier'],'100mango.QRCatcher');self.assertEqual(self.report['core_data_metadata_diagnostic']['comparison'],'differs-from-private-validator')
 def test_original_semantic_rejection_still_preserves_exact_metadata(self):
  raw=self.write({'NSManagedObjectModel_VersionHashes':{'QR':{}}});p=self.a/'Info.plist';v=plistlib.loads(p.read_bytes());v['ArchiveVersion']=999;p.write_bytes(plistlib.dumps(v))
  with self.assertRaisesRegex(m.Rejected,'archive-metadata-mismatch'):
   m.verify_archive(self.a,lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No native proof after rejection')),1000,root=self.root,clock=self.clock,report=self.report)
  self.assertEqual(bytes.fromhex(self.report['core_data_metadata_diagnostic']['raw_hex']),raw)
 def test_other_plist_parse_failure_still_captures_model(self):
  self.write({'NSManagedObjectModel_CurrentVersionName':'QR'});(self.a/'Info.plist').write_bytes(b'invalid')
  with self.assertRaises(plistlib.InvalidFileException):self.observe()
  self.assertTrue(self.report['core_data_metadata_diagnostic']['complete']);self.assertEqual(self.report['current_proof_path'],'Info.plist')
 def test_malformed_plist_retains_raw_bytes_and_stops_before_native(self):
  raw=b'not-a-plist\x00';self.path.write_bytes(raw)
  with self.assertRaises(plistlib.InvalidFileException):self.observe()
  r=self.report['core_data_metadata_diagnostic'];self.assertFalse(r['complete']);self.assertEqual(bytes.fromhex(r['raw_hex']),raw);self.assertIn('read_error',r);self.assertEqual(self.report['current_proof_path'],m.MODEL_VERSION_INFO)
  self.assertEqual(len(self.report['archive_metadata_diagnostics']),3)
 def test_non_dictionary_fails_with_exact_raw_retained(self):
  raw=self.write(['QR'])
  with self.assertRaisesRegex(m.Rejected,'model-metadata-not-dictionary'):self.observe()
  self.assertEqual(bytes.fromhex(self.report['core_data_metadata_diagnostic']['raw_hex']),raw)
 def test_non_json_float_retains_raw_and_explicit_error(self):
  raw=self.write({'unexpected':float('nan')})
  with self.assertRaises(ValueError):self.observe()
  r=self.report['core_data_metadata_diagnostic'];self.assertEqual(bytes.fromhex(r['raw_hex']),raw);self.assertNotIn('metadata',r);json.loads(m.report_bytes(self.report))
 def test_metadata_oversize_rejected_before_content_read(self):
  self.path.write_bytes(b'x'*(m.MODEL_METADATA_MAX+1))
  with patch.object(m.os,'read',side_effect=AssertionError('Oversized metadata must not be read')):
   with self.assertRaisesRegex(m.Rejected,'model-metadata-byte-limit'):self.observe()
  r=self.report['core_data_metadata_diagnostic'];self.assertFalse(r['complete']);self.assertNotIn('raw_hex',r)
 def test_exact_byte_limit_does_not_silently_truncate(self):
  self.path.write_bytes(b'x'*m.MODEL_METADATA_MAX)
  with self.assertRaises(plistlib.InvalidFileException):self.observe()
  self.assertEqual(self.report['core_data_metadata_diagnostic']['bytes'],m.MODEL_METADATA_MAX)
 def test_symlink_version_info_is_never_followed(self):
  self.path.symlink_to('QR.mom')
  with self.assertRaisesRegex(m.Rejected,'model-path-not-regular'):self.observe()
  self.assertNotIn('raw_hex',self.report['core_data_metadata_diagnostic'])
 def test_model_parent_symlink_is_never_followed(self):
  original=self.path.parent;original.rename(original.with_name('Elsewhere.momd'));original.symlink_to('Elsewhere.momd')
  catalogue=m.scan(self.a,1000,clock=self.clock)
  # Even a forged expected child cannot bypass the known linked parent.
  catalogue['paths'][m.MODEL_VERSION_INFO]={'type':'file','identity':[]}
  with self.assertRaisesRegex(m.Rejected,'model-path-not-regular'):
   m.observe_core_data_metadata(self.a,catalogue,1000,self.clock,self.report)
 def test_snapshot_hash_mismatch_is_rejected(self):
  self.write({});catalogue=m.scan(self.a,1000,clock=self.clock);catalogue['paths'][m.MODEL_VERSION_INFO]['sha256']='0'*64
  with self.assertRaisesRegex(m.Rejected,'model-snapshot-hash-mismatch'):m.observe_core_data_metadata(self.a,catalogue,1000,self.clock,self.report)
 def test_file_replaced_after_snapshot_is_rejected(self):
  self.write({});catalogue=m.scan(self.a,1000,clock=self.clock);self.path.unlink();self.write({'changed':True})
  with self.assertRaisesRegex(m.Rejected,'model-file-changed'):m.observe_core_data_metadata(self.a,catalogue,1000,self.clock,self.report)
 def test_expired_clock_stops_capture(self):
  self.write({});catalogue=m.scan(self.a,1000,clock=self.clock)
  with self.assertRaisesRegex(m.Rejected,'deadline-exceeded'):m.observe_core_data_metadata(self.a,catalogue,99,self.clock,self.report)
 def test_overflow_keeps_model_inventory_raw_and_decoded_fields(self):
  self.write({'hash':b'\x01\x02'});self.observe();r=json.loads(m.report_bytes(self.report|{'commands':['x'*(m.MAX_REPORT+1)]}))
  self.assertEqual(r['core_data_metadata_diagnostic'],self.report['core_data_metadata_diagnostic']);self.assertEqual(r['core_data_resource_observation'],self.report['core_data_resource_observation']);self.assertFalse(r['qualified'])

class OneShotDiagnosticScope(PortableTestCase):
 def identity(self):
  return {'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':m.BRANCH,'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+m.WORKFLOW+'@'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_NUMBER':'1','GITHUB_JOB':'archive','DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_EVENT_NAME':'push','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,'GITHUB_RUN_ID':'1'}
 def test_window_is_fixed_45_minutes_and_full_job_admitted(self):
  start=datetime.datetime.fromisoformat(m.WINDOW_START).timestamp();end=datetime.datetime.fromisoformat(m.WINDOW_END).timestamp()
  self.assertEqual(end-start,2700);m.authorization_window(now=start,reserve=1200);m.authorization_window(now=end-1200-1,reserve=1200)
  for when,reserve in [(start-1,0),(end,0),(end-1200,1200),(float('nan'),0),(float('inf'),0)]:
   with self.subTest(when=when),self.assertRaises(m.Rejected):m.authorization_window(now=when,reserve=reserve)
 def test_new_workflow_one_run_attempt_branch_and_no_credentials(self):
  self.assertEqual(m.BRANCH,'refs/heads/mac-model-metadata-diagnostic-20261015');self.assertEqual(m.WORKFLOW,'.github/workflows/mac-model-metadata-diagnostic.yml')
  w=(ROOT/m.WORKFLOW).read_text();self.assertIn('github.run_attempt == 1 && github.run_number == 1',w);self.assertIn('persist-credentials: false',w);self.assertIn('contents: read',w);self.assertIn('timeout-minutes: 20',w)
  for forbidden in ['secrets.','workflow_dispatch','schedule:','matrix:','codesign','exportArchive','allowProvisioning']:
   self.assertNotIn(forbidden,w)
  for key,value in [('GITHUB_RUN_NUMBER','2'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/codex/mac-unsigned-archive'),('GITHUB_WORKFLOW_REF','100mango/QRCatcher/.github/workflows/mac-unsigned-archive.yml@'+m.BRANCH),('GITHUB_WORKFLOW_SHA','b'*40)]:
   with self.subTest(key=key),self.assertRaises(m.Rejected):m.environment(self.identity()|{key:value})
 def git(self,changes=None,parent=None):
  values={('rev-parse','HEAD'):'a'*40,('rev-parse',m.BASE+'^{tree}'):m.BASE_TREE,('rev-list','--parents','-n','1','HEAD'):'a'*40+' '+(m.BASE if parent is None else parent),('status','--porcelain','--untracked-files=all'):'',('diff','--name-status',m.BASE,'HEAD','--'):'\n'.join(m.EXPECTED_DIFF if changes is None else changes),('rev-parse','HEAD^{tree}'):'c'*40}
  return lambda argv,**kw:values[tuple(argv[1:])].encode()
 def test_exact_pinned_source_and_three_file_scope(self):
  result=m.source_identity(self.identity(),self.git(),ROOT)
  self.assertEqual(result['base'],'bf726e9637fcdd469048ed157b8ea73953ccb4fb');self.assertEqual(result['app_input_count'],46);self.assertEqual(result['parents'],[m.BASE])
 def test_product_change_wrong_parent_or_extra_workflow_rejected(self):
  cases=[self.git(changes=(*m.EXPECTED_DIFF,'M\tQRCatcher.xcodeproj/project.pbxproj')),self.git(changes=(*m.EXPECTED_DIFF,'A\t.github/workflows/other.yml')),self.git(parent='b'*40),self.git(changes=tuple(x for x in m.EXPECTED_DIFF if not x.startswith('A\t')))]
  for runner in cases:
   with self.assertRaises(m.Rejected):m.source_identity(self.identity(),runner,ROOT)

if __name__=='__main__':unittest.main()
