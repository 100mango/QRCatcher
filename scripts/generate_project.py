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
        if name=='Debug':settings.update(GCC_PREPROCESSOR_DEFINITIONS=['DEBUG=1','$(inherited)'],GCC_OPTIMIZATION_LEVEL='0',ONLY_ACTIVE_ARCH='YES',GCC_SYMBOLS_PRIVATE_EXTERN='NO',ENABLE_TESTABILITY='YES',SWIFT_OPTIMIZATION_LEVEL='-Onone',SWIFT_ACTIVE_COMPILATION_CONDITIONS='DEBUG')
        else:settings.update(GCC_OPTIMIZATION_LEVEL='s',VALIDATE_PRODUCT='YES')
        refs.append(add(key+name,'XCBuildConfiguration',buildSettings=settings,name=name))
    return add(key+'configs','XCConfigurationList',buildConfigurations=refs,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
source=[]; appfiles=[]
sharedSources=[];sharedFiles=[]
for path in sorted((root/'Shared').rglob('*')):
    if path.suffix in ['.h','.m']:
        r=file(str(path.relative_to(root)),'sourcecode.c.objc' if path.suffix=='.m' else 'sourcecode.c.h');sharedFiles.append(r)
        if path.suffix=='.m':sharedSources.append(build(r))
nativeSharedSources=[];nativeSharedFiles=[]
for path in sorted((root/'Shared').rglob('*.swift')):
    r=file(str(path.relative_to(root)),'sourcecode.swift');nativeSharedFiles.append(r);nativeSharedSources.append(build(r))
source+=sharedSources;appfiles+=sharedFiles
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
    common={'HEADER_SEARCH_PATHS':['$(SRCROOT)/QRCatcher','$(SRCROOT)/Shared/Domain','$(SRCROOT)/Shared/Image'],'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':bundle,'CODE_SIGN_STYLE':'Automatic','TARGETED_DEVICE_FAMILY':'1,2','LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks @loader_path/Frameworks'}
    if key=='app':
        common.update(INFOPLIST_FILE='QRCatcher/Info.plist',ASSETCATALOG_COMPILER_APPICON_NAME='AppIcon',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        src=source;res=resources;files=appfiles;deps=[]
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES',HEADER_SEARCH_PATHS=['$(SRCROOT)/QRCatcher','$(SRCROOT)/Shared/Domain','$(SRCROOT)/Shared/Image'],IPHONEOS_DEPLOYMENT_TARGET='17.0')
        if key=='unit':common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcher.app/QRCatcher',BUNDLE_LOADER='$(TEST_HOST)')
        else:common.update(TEST_TARGET_NAME='QRCatcher')
        files=[];src=[];res=[]
        for path in sorted((root/name).glob('*.m')):
            test=file(str(path.relative_to(root)),'sourcecode.c.objc');files.append(test);src.append(build(test))
        if key=='unit':
            for entry in json.loads((root/'Tests/Fixtures/manifest.json').read_text()):
                r=file('Tests/Fixtures/'+entry['name'],'image.png');files.append(r);res.append(build(r))
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=appID,remoteInfo='QRCatcher')
        deps=[add(key+'dependency','PBXTargetDependency',target=appID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
# Native macOS executable and supported hosted XCTest/UI routes, independent of the iOS target.
macID=uid('mac')
for key,name,kind in [('mac','QRCatcherMac','application'),('macunit','QRCatcherMacTests','bundle.unit-test'),('macui','QRCatcherMacUITests','bundle.ui-testing')]:
    app=key=='mac';ext='app' if app else 'xctest'
    product=add(key+'product','PBXFileReference',explicitFileType='wrapper.application' if app else 'wrapper.cfbundle',includeInIndex=0,path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR');products.append(product)
    files=[];src=[];res=[];deps=[]
    for path in sorted((root/name).glob('*.swift')):
        r=file(str(path.relative_to(root)),'sourcecode.swift');files.append(r);src.append(build(r))
    common={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':'100mango.QRCatcher' if app else '100mango.'+name,'SDKROOT':'macosx','SUPPORTED_PLATFORMS':'macosx','MACOSX_DEPLOYMENT_TARGET':'13.0','SWIFT_VERSION':'5.0','SWIFT_STRICT_CONCURRENCY':'targeted','HEADER_SEARCH_PATHS':['$(SRCROOT)/QRCatcher','$(SRCROOT)/Shared/Domain','$(SRCROOT)/Shared/Image'],'LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/../Frameworks @loader_path/../Frameworks','CODE_SIGN_STYLE':'Automatic','ENABLE_HARDENED_RUNTIME':'NO'}
    if app:
        common.update(INFOPLIST_FILE='QRCatcherMac/Info.plist',CODE_SIGN_ENTITLEMENTS='QRCatcherMac/QRCatcherMac.entitlements',ASSETCATALOG_COMPILER_APPICON_NAME='AppIcon',ASSETCATALOG_COMPILER_STANDALONE_ICON_BEHAVIOR='all',SWIFT_OBJC_BRIDGING_HEADER='QRCatcherMac/QRCatcherMac-Bridging-Header.h',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        src+=sharedSources+nativeSharedSources+[build(model)];files+=sharedFiles+nativeSharedFiles+[model]
        for path in ['QRCatcher/QRHistoryStore.m','QRCatcher/URLEntity.m']:
            r=file(path,'sourcecode.c.objc');files.append(r);src.append(build(r))
        r=file('QRCatcher/PrivacyInfo.xcprivacy','text.xml');files.append(r);res.append(build(r))
        r=file('QRCatcherMac/Assets.xcassets','folder.assetcatalog');files.append(r);res.append(build(r))
        for localizedName in ['Localizable.strings','InfoPlist.strings']:
            localized=add('maclocalized:'+localizedName,'PBXFileReference',lastKnownFileType='text.plist.strings',name='zh-Hans',path='QRCatcherMac/zh-Hans.lproj/'+localizedName,sourceTree='<group>')
            variant=add('macvariant:'+localizedName,'PBXVariantGroup',children=[localized],name=localizedName,sourceTree='<group>');files.append(variant);res.append(build(variant))
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES',MACOSX_DEPLOYMENT_TARGET='14.0')
        if key=='macunit':
            r=file('Tests/Support/QRManagedStoreTestCase.swift','sourcecode.swift');files.append(r);src.append(build(r))
            common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcherMac.app/Contents/MacOS/QRCatcherMac',BUNDLE_LOADER='$(TEST_HOST)')
            for entry in json.loads((root/'Tests/Fixtures/manifest.json').read_text()):
                r=file('Tests/Fixtures/'+entry['name'],'image.png');files.append(r);res.append(build(r))
        else:common.update(TEST_TARGET_NAME='QRCatcherMac')
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=macID,remoteInfo='QRCatcherMac')
        deps=[add(key+'dependency','PBXTargetDependency',target=macID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
# Native visionOS has an import-first workflow; there is no passthrough-camera claim.
visionID=uid('vision')
for key,name,kind in [('vision','QRCatcherVision','application'),('visionunit','QRCatcherVisionTests','bundle.unit-test'),('visionui','QRCatcherVisionUITests','bundle.ui-testing')]:
    app=key=='vision';ext='app' if app else 'xctest'
    product=add(key+'product','PBXFileReference',explicitFileType='wrapper.application' if app else 'wrapper.cfbundle',includeInIndex=0,path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR');products.append(product)
    files=[];src=[];res=[];deps=[]
    for path in sorted((root/name).glob('*.swift')):
        r=file(str(path.relative_to(root)),'sourcecode.swift');files.append(r);src.append(build(r))
    common={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':'100mango.QRCatcher' if app else '100mango.'+name,'SDKROOT':'xros','SUPPORTED_PLATFORMS':'xros xrsimulator','TARGETED_DEVICE_FAMILY':'7','XROS_DEPLOYMENT_TARGET':'1.0','SWIFT_VERSION':'5.0','SWIFT_STRICT_CONCURRENCY':'targeted','HEADER_SEARCH_PATHS':['$(SRCROOT)/QRCatcher','$(SRCROOT)/Shared/Domain','$(SRCROOT)/Shared/Image'],'LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks @loader_path/Frameworks','CODE_SIGN_STYLE':'Automatic'}
    if app:
        common.update(INFOPLIST_FILE='QRCatcherVision/Info.plist',SWIFT_OBJC_BRIDGING_HEADER='QRCatcherVision/QRCatcherVision-Bridging-Header.h',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        src+=sharedSources+nativeSharedSources+[build(model)];files+=sharedFiles+nativeSharedFiles+[model]
        for path in ['QRCatcher/QRHistoryStore.m','QRCatcher/URLEntity.m','QRCatcherMac/MacHistory.swift','QRCatcherMac/MacLocalization.swift']:
            r=file(path,'sourcecode.c.objc' if path.endswith('.m') else 'sourcecode.swift');files.append(r);src.append(build(r))
        r=file('QRCatcher/PrivacyInfo.xcprivacy','text.xml');files.append(r);res.append(build(r))
        localized=add('visionlocalized:Localizable.strings','PBXFileReference',lastKnownFileType='text.plist.strings',name='zh-Hans',path='QRCatcherMac/zh-Hans.lproj/Localizable.strings',sourceTree='<group>')
        variant=add('visionvariant:Localizable.strings','PBXVariantGroup',children=[localized],name='Localizable.strings',sourceTree='<group>');files.append(variant);res.append(build(variant))
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES')
        if key=='visionunit':
            r=file('Tests/Support/QRManagedStoreTestCase.swift','sourcecode.swift');files.append(r);src.append(build(r))
            common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcherVision.app/QRCatcherVision',BUNDLE_LOADER='$(TEST_HOST)')
            for entry in json.loads((root/'Tests/Fixtures/manifest.json').read_text()):
                r=file('Tests/Fixtures/'+entry['name'],'image.png');files.append(r);res.append(build(r))
        else:common.update(TEST_TARGET_NAME='QRCatcherVision')
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=visionID,remoteInfo='QRCatcherVision')
        deps=[add(key+'dependency','PBXTargetDependency',target=visionID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
# Native TV uses PhotoKit and bounded metadata, never the phone SQLite store.
tvID=uid('tv')
for key,name,kind in [('tv','QRCatcherTV','application'),('tvunit','QRCatcherTVTests','bundle.unit-test'),('tvui','QRCatcherTVUITests','bundle.ui-testing')]:
    app=key=='tv';ext='app' if app else 'xctest'
    product=add(key+'product','PBXFileReference',explicitFileType='wrapper.application' if app else 'wrapper.cfbundle',includeInIndex=0,path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR');products.append(product)
    files=[];src=[];res=[];deps=[]
    for path in sorted((root/name).glob('*.swift')):
        r=file(str(path.relative_to(root)),'sourcecode.swift');files.append(r);src.append(build(r))
    common={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':'100mango.QRCatcher' if app else '100mango.'+name,'SDKROOT':'appletvos','SUPPORTED_PLATFORMS':'appletvos appletvsimulator','TARGETED_DEVICE_FAMILY':'3','TVOS_DEPLOYMENT_TARGET':'17.0','SWIFT_VERSION':'5.0','SWIFT_STRICT_CONCURRENCY':'targeted','HEADER_SEARCH_PATHS':['$(SRCROOT)/QRCatcher','$(SRCROOT)/Shared/Domain','$(SRCROOT)/Shared/Image'],'LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks @loader_path/Frameworks','CODE_SIGN_STYLE':'Automatic'}
    if app:
        common.update(INFOPLIST_FILE='QRCatcherTV/Info.plist',SWIFT_OBJC_BRIDGING_HEADER='QRCatcherTV/QRCatcherTV-Bridging-Header.h',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        src+=sharedSources+nativeSharedSources;files+=sharedFiles+nativeSharedFiles
        for path in ['QRCatcherMac/MacLocalization.swift']:
            r=file(path,'sourcecode.c.objc' if path.endswith('.m') else 'sourcecode.swift');files.append(r);src.append(build(r))
        r=file('QRCatcherTV/PrivacyInfo.xcprivacy','text.xml');files.append(r);res.append(build(r))
        localized=add('tvlocalized:Localizable.strings','PBXFileReference',lastKnownFileType='text.plist.strings',name='zh-Hans',path='QRCatcherMac/zh-Hans.lproj/Localizable.strings',sourceTree='<group>')
        variant=add('tvvariant:Localizable.strings','PBXVariantGroup',children=[localized],name='Localizable.strings',sourceTree='<group>');files.append(variant);res.append(build(variant))
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES')
        if key=='tvunit':
            common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcherTV.app/QRCatcherTV',BUNDLE_LOADER='$(TEST_HOST)')
            for entry in json.loads((root/'Tests/Fixtures/manifest.json').read_text()):
                r=file('Tests/Fixtures/'+entry['name'],'image.png');files.append(r);res.append(build(r))
        else:common.update(TEST_TARGET_NAME='QRCatcherTV')
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=tvID,remoteInfo='QRCatcherTV')
        deps=[add(key+'dependency','PBXTargetDependency',target=tvID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
# Native single-target Watch app. Source IDs are drafts; no portal registration.
watchID=uid('watch')
for key,name,kind in [('watch','QRCatcherWatch','application'),('watchunit','QRCatcherWatchTests','bundle.unit-test'),('watchui','QRCatcherWatchUITests','bundle.ui-testing')]:
    app=key=='watch';ext='app' if app else 'xctest'
    product=add(key+'product','PBXFileReference',explicitFileType='wrapper.application' if app else 'wrapper.cfbundle',includeInIndex=0,path=name+'.'+ext,sourceTree='BUILT_PRODUCTS_DIR');products.append(product)
    files=[];src=[];res=[];deps=[]
    for path in sorted((root/name).glob('*.swift')):
        r=file(str(path.relative_to(root)),'sourcecode.swift');files.append(r);src.append(build(r))
    common={'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':'100mango.QRCatcher.watchkitapp' if app else '100mango.'+name,'SDKROOT':'watchos','SUPPORTED_PLATFORMS':'watchos watchsimulator','TARGETED_DEVICE_FAMILY':'4','WATCHOS_DEPLOYMENT_TARGET':'9.0','SWIFT_VERSION':'5.0','SWIFT_STRICT_CONCURRENCY':'targeted','LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks @loader_path/Frameworks','CODE_SIGN_STYLE':'Automatic'}
    if app:
        common.update(INFOPLIST_FILE='QRCatcherWatch/Info.plist',MARKETING_VERSION='1.1',CURRENT_PROJECT_VERSION='2')
        localized=add('watchlocalized:Localizable.strings','PBXFileReference',lastKnownFileType='text.plist.strings',name='zh-Hans',path='QRCatcherWatch/zh-Hans.lproj/Localizable.strings',sourceTree='<group>')
        variant=add('watchvariant:Localizable.strings','PBXVariantGroup',children=[localized],name='Localizable.strings',sourceTree='<group>');files.append(variant);res.append(build(variant))
        r=file('Shared/Services/QRPrivacyText.swift','sourcecode.swift');files.append(r);src.append(build(r))
        r=file('QRCatcher/PrivacyInfo.xcprivacy','text.xml');files.append(r);res.append(build(r))
    else:
        common.update(GENERATE_INFOPLIST_FILE='YES')
        if key=='watchunit':
            common.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/QRCatcherWatch.app/QRCatcherWatch',BUNDLE_LOADER='$(TEST_HOST)')
            for entry in json.loads((root/'Tests/Fixtures/manifest.json').read_text()):
                r=file('Tests/Fixtures/'+entry['name'],'image.png');files.append(r);res.append(build(r))
        else:common.update(TEST_TARGET_NAME='QRCatcherWatch')
        proxy=add(key+'proxy','PBXContainerItemProxy',containerPortal=projectID,proxyType=1,remoteGlobalIDString=watchID,remoteInfo='QRCatcherWatch')
        deps=[add(key+'dependency','PBXTargetDependency',target=watchID,targetProxy=proxy)]
    groups.append(add(key+'group','PBXGroup',children=files,name=name,sourceTree='<group>'))
    targets.append(add(key,'PBXNativeTarget',buildConfigurationList=configs(key,common),buildPhases=[phase(key+'sources','Sources',src),phase(key+'frameworks','Frameworks',[]),phase(key+'resources','Resources',res)],buildRules=[],dependencies=deps,name=name,productName=name,productReference=product,productType='com.apple.product-type.'+kind))
# A file reference has one navigator owner even when several targets compile it.
from collections import Counter
counts=Counter(r for group in groups for r in objects[group]['children'])
commonRefs=[r for r,n in counts.items() if n>1]
for group in groups:objects[group]['children']=[r for r in objects[group]['children'] if counts[r]==1]
groups.append(add('sharedgroup','PBXGroup',children=commonRefs,name='Shared sources and test fixtures',sourceTree='<group>'))
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

macScheme=(root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherMac.xcscheme')
macScheme.write_text(scheme.read_text().replace(uid('app'),uid('mac')).replace(uid('unit'),uid('macunit')).replace(uid('ui'),uid('macui')).replace('QRCatcherTests','QRCatcherMacTests').replace('QRCatcherUITests','QRCatcherMacUITests').replace('BuildableName="QRCatcher.app"','BuildableName="QRCatcherMac.app"').replace('BlueprintName="QRCatcher"','BlueprintName="QRCatcherMac"'))

visionScheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherVision.xcscheme'
visionScheme.write_text(scheme.read_text().replace(uid('app'),uid('vision')).replace(uid('unit'),uid('visionunit')).replace(uid('ui'),uid('visionui')).replace('QRCatcherTests','QRCatcherVisionTests').replace('QRCatcherUITests','QRCatcherVisionUITests').replace('BuildableName="QRCatcher.app"','BuildableName="QRCatcherVision.app"').replace('BlueprintName="QRCatcher"','BlueprintName="QRCatcherVision"'))

# The sandbox gate uses a separate test bundle and a separate derived-data path.
sandboxScheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherMacSandbox.xcscheme'
sandboxScheme.write_text(macScheme.read_text().replace(f'<TestableReference skipped="NO">{ref("macunit","QRCatcherMacTests.xctest")}</TestableReference>', ''))

tvScheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherTV.xcscheme'
tvScheme.write_text(scheme.read_text().replace(uid('app'),uid('tv')).replace(uid('unit'),uid('tvunit')).replace(uid('ui'),uid('tvui')).replace('QRCatcherTests','QRCatcherTVTests').replace('QRCatcherUITests','QRCatcherTVUITests').replace('BuildableName="QRCatcher.app"','BuildableName="QRCatcherTV.app"').replace('BlueprintName="QRCatcher"','BlueprintName="QRCatcherTV"'))

watchScheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherWatch.xcscheme'
watchScheme.write_text(scheme.read_text().replace(uid('app'),uid('watch')).replace(uid('unit'),uid('watchunit')).replace(uid('ui'),uid('watchui')).replace('QRCatcherTests','QRCatcherWatchTests').replace('QRCatcherUITests','QRCatcherWatchUITests').replace('BuildableName="QRCatcher.app"','BuildableName="QRCatcherWatch.app"').replace('BlueprintName="QRCatcher"','BlueprintName="QRCatcherWatch"'))
