"""Portable regression checks for the missing-declared-iPad-icon failure."""
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_ios_icons as icons
import ios_icon_archive as archive

def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
def png(size,cgbi=False):
    data=b'\x89PNG\r\n\x1a\n'
    if cgbi:data+=chunk(b'CgBI',b'\x40\xa0\x60\x82')
    return data+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x60\xa0'*size)*size))+chunk(b'IEND',b'')

def source_fixture(root):
    shutil.copytree(ROOT/icons.CATALOG,root/icons.CATALOG)
    (root/'scripts').mkdir()
    shutil.copyfile(ROOT/'scripts/ipad_icon_manifest.json',root/'scripts/ipad_icon_manifest.json')

class SourceIcons(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();source_fixture(self.root)
        self.addCleanup(self.tmp.cleanup)
    def test_all_declared_images_and_nine_exact_rgb_assets(self):
        result=icons.source_icons(self.root)
        self.assertEqual(result['ipad_images'],9);self.assertEqual(len(result['declared_images']),16)
        self.assertTrue(all(x['color_type']==2 for x in result['declared_images'] if x['idiom']=='ipad'))
    def test_missing_required_declared_icon_fails(self):
        (self.root/icons.CATALOG/'ipad-76x76@2x.png').unlink()
        with self.assertRaisesRegex(ValueError,'missing icon input'):icons.source_icons(self.root)
    def test_wrong_dimensions_fail_before_archive(self):
        (self.root/icons.CATALOG/'ipad-83.5x83.5@2x.png').write_bytes(png(152))
        with self.assertRaisesRegex(ValueError,'dimensions differ'):icons.source_icons(self.root)
    def test_same_dimensions_changed_artwork_fails_pinned_bytes(self):
        p=self.root/icons.CATALOG/'ipad-76x76@2x.png';raw=p.read_bytes();needle=b'sRGB\x00';self.assertIn(needle,raw)
        p.write_bytes(png(152))
        with self.assertRaises(ValueError):icons.source_icons(self.root)
    def test_linked_declared_icon_is_rejected(self):
        p=self.root/icons.CATALOG/'ipad-76x76@2x.png';p.unlink();p.symlink_to(self.root/icons.CATALOG/'ipad-83.5x83.5@2x.png')
        with self.assertRaisesRegex(ValueError,'unsafe'):icons.source_icons(self.root)
    def test_existing_materializer_is_read_only_and_needs_no_pillow_or_sips(self):
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/icons.CATALOG).iterdir() if p.is_file()}
        result=subprocess.run([sys.executable,str(ROOT/'scripts/materialize_ipad_icons.py')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/icons.CATALOG).iterdir() if p.is_file()}
        self.assertEqual(before,after)
        text=(ROOT/'scripts/materialize_ipad_icons.py').read_text();self.assertNotIn('sips',text);self.assertNotIn('PIL',text)

def pro_rendition():
    return {'AssetType':'Icon Image','Name':'AppIcon','Idiom':'pad','Scale':2,
            'PixelWidth':167,'PixelHeight':167,'Opaque':True,'ColorModel':'RGB',
            'RenditionName':'ipad-83.5x83.5@2x.png'}

class BuiltIcons(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=Path(self.tmp.name).resolve()/'QRCatcher.app';self.app.mkdir()
        self.info={'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcher',
            'CFBundleShortVersionString':'1.1','CFBundleVersion':'3','UIDeviceFamily':[1,2],
            'DTPlatformName':'iphoneos','CFBundleIcons~ipad':{'CFBundlePrimaryIcon':{
                'CFBundleIconName':'AppIcon','CFBundleIconFiles':['AppIcon60x60','AppIcon76x76']}}}
        self.write_info();(self.app/'Assets.car').write_bytes(b'synthetic CAR inventory supplied separately')
        for name,size in [('AppIcon60x60@2x.png',120),('AppIcon76x76@2x~ipad.png',152)]:
            (self.app/name).write_bytes(png(size,cgbi=True))
        self.car=[pro_rendition()]
    def write_info(self):(self.app/'Info.plist').write_bytes(plistlib.dumps(self.info))
    def test_referenced_loose_152_and_exact_named_catalog_167(self):
        result=icons.built_icons(self.app,self.car)
        self.assertEqual(result['required_referenced_png_dimensions'],[152])
        self.assertEqual(result['required_named_catalog_dimensions'],[167])
        self.assertEqual(result['observed_ipad_dimensions'],[120,152,167])
        self.assertEqual(result['ipad_pro_catalog_renditions'],self.car)
        self.assertTrue(all('CgBI' in x['chunks'] for x in result['loose_pngs']))
    def test_old_ipa_shape_is_rejected_even_with_assets_car(self):
        self.info['CFBundleIcons~ipad']['CFBundlePrimaryIcon'].pop('CFBundleIconFiles');self.write_info()
        with self.assertRaisesRegex(ValueError,'file references'):icons.built_icons(self.app,self.car)
    def test_missing_catalog_rendition_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[])
    def test_unrelated_catalog_name_does_not_satisfy_ipad_pro(self):
        for name in ('Unrelated','AppIconAlternate','AppIcon-167'):
            with self.subTest(name=name):
                row=pro_rendition();row['Name']=name
                with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[row])
    def test_wrong_idiom_does_not_satisfy_ipad_pro(self):
        for idiom in ('phone','marketing','universal'):
            with self.subTest(idiom=idiom):
                row=pro_rendition();row['Idiom']=idiom
                with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[row])
    def test_wrong_scale_does_not_satisfy_ipad_pro(self):
        for scale in (1,3,2.0,'2',True,None):
            with self.subTest(scale=scale):
                row=pro_rendition();row['Scale']=scale
                with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[row])
    def test_mismatched_built_info_name_is_rejected(self):
        self.info['CFBundleIcons~ipad']['CFBundlePrimaryIcon']['CFBundleIconName']='AnotherIcon';self.write_info()
        row=pro_rendition();row['Name']='AnotherIcon'
        with self.assertRaisesRegex(ValueError,'file references'):icons.built_icons(self.app,[row])
    def test_unrelated_loose_167_cannot_substitute_for_catalog(self):
        (self.app/'Unrelated167.png').write_bytes(png(167))
        with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[])
    def test_wrong_rendition_type_name_dimensions_or_opacity_is_rejected(self):
        for key,value in [('AssetType','Image'),('RenditionName','other167.png'),('PixelWidth',152),
                          ('PixelHeight',166),('PixelWidth',167.0),('Opaque',False),('Opaque',1),('ColorModel','Gray')]:
            with self.subTest(key=key,value=value):
                row=pro_rendition();row[key]=value
                with self.assertRaisesRegex(ValueError,'167x167 catalog'):icons.built_icons(self.app,[row])
    def test_missing_152_cannot_be_satisfied_by_unlinked_png(self):
        (self.app/'AppIcon76x76@2x~ipad.png').write_bytes(png(120));(self.app/'Unrelated152.png').write_bytes(png(152))
        with self.assertRaisesRegex(ValueError,'152x152'):icons.built_icons(self.app,self.car)
    def test_wrong_reference_and_old_build_are_rejected(self):
        self.info['CFBundleVersion']='2';self.write_info()
        with self.assertRaisesRegex(ValueError,'build 3'):icons.built_icons(self.app,self.car)
        self.info['CFBundleVersion']='3';self.info['CFBundleIcons~ipad']['CFBundlePrimaryIcon']['CFBundleIconFiles']=['Absent'];self.write_info()
        with self.assertRaisesRegex(ValueError,'no actual PNG'):icons.built_icons(self.app,self.car)
    def test_corrupt_png_is_rejected(self):
        (self.app/'AppIcon76x76@2x~ipad.png').write_bytes(png(152)[:-5])
        with self.assertRaises(ValueError):icons.built_icons(self.app,self.car)

class ArchivePreflight(unittest.TestCase):
    def test_missing_declared_icon_stops_before_any_xcodebuild(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();source_fixture(root)
            (root/icons.CATALOG/'ipad-76x76@2x.png').unlink();calls=[]
            env={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':archive.BRANCH,'GITHUB_EVENT_NAME':'push',
                'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+archive.WORKFLOW+'@'+archive.BRANCH,
                'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,
                'GITHUB_RUN_ID':'123','QR_ICON_JOB_STARTED':'100'}
            def runner(*args,**kwargs):calls.append(args);raise AssertionError('no native command before valid source icons')
            with patch.object(archive,'source_snapshot',return_value={'source':'a'*40}):
                result=archive.execute(root,env,clock=lambda:110.,runner=runner)
            self.assertFalse(result['qualified']);self.assertEqual(calls,[])
            self.assertIn('missing icon input',result['failure']['reason'])
    def test_fixed_archive_is_ios_only_unsigned_and_never_runs_ui(self):
        args=archive.archive_command()
        self.assertEqual(args[:4],['xcodebuild','archive','-project','QRCatcher-iOS-Only.xcodeproj'])
        self.assertIn('CODE_SIGNING_ALLOWED=NO',args);self.assertIn('CODE_SIGNING_REQUIRED=NO',args)
        self.assertNotIn('-allowProvisioningUpdates',args);self.assertNotIn('test',args)
        self.assertNotIn('codex/',archive.BRANCH)

class ArchivePipeline(unittest.TestCase):
    def execute(self, wrapper_error=False, source_changed=False, missing_catalog=False, source_check_failure=False, archive_uncertain=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve();source_fixture(root)
        identity={'source':'a'*40,'tree':'b'*40};calls=[]
        env={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':archive.BRANCH,'GITHUB_EVENT_NAME':'push',
            'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive','GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+archive.WORKFLOW+'@'+archive.BRANCH,
            'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer','GITHUB_SHA':'a'*40,'GITHUB_WORKFLOW_SHA':'a'*40,
            'GITHUB_RUN_ID':'123','QR_ICON_JOB_STARTED':'100'}
        def runner(args,**kwargs):
            calls.append(args);out=b'';err=b''
            if args==['xcodebuild','-version']:out=b'Xcode 27.0\nBuild version 27A266a\n'
            elif args==archive.archive_command():
                if archive_uncertain:raise archive.CaptureStopped('archive timed out',cleanup_confirmed=False)
                app=root/archive.APP;app.mkdir(parents=True)
                info={'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcher','CFBundleShortVersionString':'1.1',
                    'CFBundleVersion':'3','UIDeviceFamily':[1,2],'DTPlatformName':'iphoneos',
                    'CFBundleIcons~ipad':{'CFBundlePrimaryIcon':{'CFBundleIconName':'AppIcon',
                    'CFBundleIconFiles':['AppIcon76x76']}}}
                (app/'Info.plist').write_bytes(plistlib.dumps(info));(app/'Assets.car').write_bytes(b'synthetic')
                for name,size in [('AppIcon76x76@2x~ipad.png',152)]:
                    (app/name).write_bytes(png(size,cgbi=True))
                out=b'** ARCHIVE SUCCEEDED **\n'
                if wrapper_error:err=b'x'*(300*1024)+b'\nerror: retained full-stream wrapper failure\n'+b'x'*(300*1024)
            elif args[:3]==['xcrun','assetutil','--info']:out=json.dumps([] if missing_catalog else [pro_rendition()]).encode()
            else:self.assertIn('unittest',args)
            return subprocess.CompletedProcess(args,0,out,err)
        snapshots=[identity,ValueError('source host read failed') if source_check_failure else ({**identity,'tree':'c'*40} if source_changed else identity)]
        with patch.object(archive,'source_snapshot',side_effect=snapshots) as snapshot,patch.object(archive,'verify_package',return_value={'status':'pass'}) as package:
            result=archive.execute(root,env,clock=lambda:110.,runner=runner)
            if not wrapper_error and not archive_uncertain:package.assert_called_once_with(root/archive.ARCHIVE,'device','Release')
            self.assertEqual(snapshot.call_count,1 if archive_uncertain else 2)
        return result,calls
    def test_one_archive_qualifies_only_with_built_pngs_and_same_source(self):
        result,calls=self.execute()
        self.assertTrue(result['qualified'],result.get('failure'));self.assertEqual(calls.count(archive.archive_command()),1)
        self.assertEqual(result['source_before'],result['source_after'])
        self.assertEqual(result['built_icons']['required_referenced_png_dimensions'],[152])
        self.assertFalse(result['signing_qualified']);self.assertFalse(result['binary_handoff'])
    def test_complete_stderr_is_scanned_even_when_middle_is_not_retained(self):
        result,calls=self.execute(wrapper_error=True)
        self.assertFalse(result['qualified']);self.assertEqual(result['failure']['reason'],'archive reported error')
        self.assertTrue(result['commands'][-1]['stderr']['truncated']);self.assertTrue(result['commands'][-1]['reported_error'])
        self.assertEqual(result['source_before'],result['source_after'])
        self.assertFalse(any(x[:3]==['xcrun','assetutil','--info'] for x in calls))
    def test_post_archive_source_change_cannot_qualify(self):
        result,_=self.execute(source_changed=True)
        self.assertFalse(result['qualified']);self.assertEqual(result['failure']['reason'],'archive changed tested source inputs')
    def test_inspection_failure_still_records_host_source_after(self):
        result,calls=self.execute(missing_catalog=True)
        self.assertFalse(result['qualified']);self.assertIn('167x167 catalog',result['failure']['reason'])
        self.assertEqual(result['source_before'],result['source_after'])
        self.assertEqual(calls.count(archive.archive_command()),1)
    def test_source_failure_is_separate_and_preserves_inspection_failure(self):
        result,_=self.execute(missing_catalog=True,source_check_failure=True)
        self.assertIn('167x167 catalog',result['failure']['reason'])
        self.assertEqual(result['source_after_failure']['reason'],'source host read failed')
        self.assertFalse(result['qualified'])
    def test_source_mismatch_is_separate_and_preserves_inspection_failure(self):
        result,_=self.execute(missing_catalog=True,source_changed=True)
        self.assertIn('167x167 catalog',result['failure']['reason'])
        self.assertEqual(result['source_after_failure']['reason'],'archive changed tested source inputs')
    def test_uncertain_archive_does_not_run_source_after(self):
        result,calls=self.execute(archive_uncertain=True)
        self.assertFalse(result['qualified']);self.assertNotIn('source_after',result)
        self.assertFalse(any(x[:3]==['xcrun','assetutil','--info'] for x in calls))

if __name__=='__main__':unittest.main()
