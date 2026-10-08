#!/usr/bin/env python3
"""Dependency-free deterministic project definition. Run after adding source files."""
import hashlib,json,pathlib
root=pathlib.Path(__file__).resolve().parent.parent
objects={}
def uid(s): return hashlib.sha1(s.encode()).hexdigest()[:24].upper()
def add(key,isa,**kw):
    ident=uid(key);objects[ident]={'isa':isa,**kw};return ident
def file(path,typ): return add('file:'+path,'PBXFileReference',lastKnownFileType=typ,path=path,sourceTree='<group>')
def build(ref): return add('build:'+ref,'PBXBuildFile',fileRef=ref)
def phase(key,kind,files): return add(key,'PBX'+kind+'BuildPhase',buildActionMask=2147483647,files=files,runOnlyForDeploymentPostprocessing=0)
def configs(key,common):
    refs=[]
    for name in ['Debug','Release']:
        settings=dict(common)
        if name=='Debug':settings.update(GCC_PREPROCESSOR_DEFINITIONS=['DEBUG=1','$(inherited)'],GCC_OPTIMIZATION_LEVEL='0',ONLY_ACTIVE_ARCH='YES',GCC_SYMBOLS_PRIVATE_EXTERN='NO',ENABLE_TESTABILITY='YES')
        else:settings.update(GCC_OPTIMIZATION_LEVEL='s',VALIDATE_PRODUCT='YES')
        refs.append(add(key+name,'XCBuildConfiguration',buildSettings=settings,name=name))
    return add(key+'configs','XCConfigurationList',buildConfigurations=refs,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
source=[]; appfiles=[]
for path in sorted((root/'QRCatcher').glob('*')):
    if path.suffix in ['.h','.m']:
        ref=file(str(path.relative_to(root)),'sourcecode.c.objc' if path.suffix=='.m' else 'sourcecode.c.h');appfiles.append(ref)
        if path.suffix=='.m':source.append(build(ref))
model=file('QRCatcher/QR.xcdatamodeld','wrapper.xcdatamodeld');source.append(build(model));appfiles.append(model)
resources=[]
for name in ['Localizable.strings','InfoPlist.strings']:
    localized=add('localized:'+name,'PBXFileReference',lastKnownFileType='text.plist.strings',name='zh-Hans',path='QRCatcher/zh-Hans.lproj/'+name,sourceTree='<group>')
    variant=add('variant:'+name,'PBXVariantGroup',children=[localized],name=name,sourceTree='<group>')
    appfiles.append(variant);resources.append(build(variant))
for p,t in [('QRCatcher/Images.xcassets','folder.assetcatalog'),('QRCatcher/Base.lproj/LaunchScreen.xib','file.xib'),('QRCatcher/PrivacyInfo.xcprivacy','text.xml')]:
    r=file(p,t); appfiles.append(r);resources.append(build(r))
products=[];targets=[];groups=[]
projectID=uid('project'); appID=uid('app')
for key,name,bundle,kind in [('app','QRCatcher','100mango.QRCatcher','application'),('unit','QRCatcherTests','100mango.QRCatcherTests','bundle.unit-test'),('ui','QRCatcherUITests','100mango.QRCatcherUITests','bundle.ui-testing')]:
    ext='app' if key=='app' else 'xctest'
    product=add(key+'product','PBXFileReference',explicitFileType='wrapper.application' if key=='app' else 'wrapper.cfbundle',includeInIndex=0,path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR');products.append(product)
    common={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':bundle,'CODE_SIGN_STYLE':'Automatic','TARGETED_DEVICE_FAMILY':'1','LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks @loader_path/Frameworks'}
    if key=='app':
        common.update(INFOPLIST_FILE='QRCatcher/Info.plist',ASSETCATALOG_COMPILER_APPICON_NAME='AppIcon',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        src=source;res=resources;files=appfiles;deps=[]
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES',HEADER_SEARCH_PATHS='$(SRCROOT)/QRCatcher',IPHONEOS_DEPLOYMENT_TARGET='17.0')
        if key=='unit':common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcher.app/QRCatcher',BUNDLE_LOADER='$(TEST_HOST)')
        else:common.update(TEST_TARGET_NAME='QRCatcher')
        test=file(name+'/'+name+'.m','sourcecode.c.objc');files=[test];src=[build(test)];res=[]
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=appID,remoteInfo='QRCatcher')
        deps=[add(key+'dependency','PBXTargetDependency',target=appID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
productsID=add('products','PBXGroup',children=products,name='Products',sourceTree='<group>')
main=add('main','PBXGroup',children=groups+[productsID],sourceTree='<group>')
projectSettings={'CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','CLANG_WARN_BOOL_CONVERSION':'YES','CLANG_WARN_CONSTANT_CONVERSION':'YES','CLANG_WARN_ENUM_CONVERSION':'YES','CLANG_WARN_INT_CONVERSION':'YES','CLANG_WARN_OBJC_ROOT_CLASS':'YES_ERROR','GCC_WARN_ABOUT_RETURN_TYPE':'YES_ERROR','GCC_WARN_UNUSED_VARIABLE':'YES','IPHONEOS_DEPLOYMENT_TARGET':'15.0','SDKROOT':'iphoneos','ENABLE_USER_SCRIPT_SANDBOXING':'YES','GCC_C_LANGUAGE_STANDARD':'gnu11','CLANG_CXX_LANGUAGE_STANDARD':'gnu++17','DEBUG_INFORMATION_FORMAT':'dwarf-with-dsym'}
add('project','PBXProject',attributes={'LastUpgradeCheck':'2700','TargetAttributes':{appID:{'CreatedOnToolsVersion':'27.0'},uid('unit'):{'TestTargetID':appID},uid('ui'):{'TestTargetID':appID}}},buildConfigurationList=configs('project',projectSettings),compatibilityVersion='Xcode 14.0',developmentRegion='en',knownRegions=['en','Base','zh-Hans'],mainGroup=main,productRefGroup=productsID,projectDirPath='',projectRoot='',targets=targets)
def emit(x):
    if isinstance(x,dict):return '{\n'+''.join(json.dumps(str(k))+ ' = '+emit(v)+';\n' for k,v in x.items())+'}'
    if isinstance(x,list):return '('+','.join(emit(v) for v in x)+')'
    if isinstance(x,int):return str(x)
    return json.dumps(x,ensure_ascii=False)
(root/'QRCatcher.xcodeproj/project.pbxproj').write_text('// !$*UTF8*$!\n'+emit({'archiveVersion':1,'classes':{},'objectVersion':56,'objects':objects,'rootObject':projectID})+'\n')
scheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcher.xcscheme';scheme.parent.mkdir(parents=True,exist_ok=True)
def ref(key,name):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{uid(key)}" BuildableName="{name}" BlueprintName="{name.split(".")[0]}" ReferencedContainer="container:QRCatcher.xcodeproj"/>'
scheme.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.7">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref('app','QRCatcher.app')}</BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO">{ref('unit','QRCatcherTests.xctest')}</TestableReference><TestableReference skipped="NO">{ref('ui','QRCatcherUITests.xctest')}</TestableReference></Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref('app','QRCatcher.app')}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref('app','QRCatcher.app')}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''')
