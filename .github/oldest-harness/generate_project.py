#!/usr/bin/env python3
"""Standalone iOS 15 UI runner; it never builds or links the apps under test."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
objects = {}
def uid(value): return hashlib.sha256(value.encode()).hexdigest()[:24].upper()
def add(key, isa, **values):
    identifier = uid(key)
    objects[identifier] = {"isa": isa, **values}
    return identifier
def configs(key, settings):
    entries = [add(key + name, "XCBuildConfiguration", name=name, buildSettings=settings) for name in ["Debug", "Release"]]
    return add(key + "Configs", "XCConfigurationList", buildConfigurations=entries, defaultConfigurationIsVisible=0, defaultConfigurationName="Debug")
def phase(key, kind, files):
    return add(key, "PBX" + kind + "BuildPhase", buildActionMask=2147483647, files=files, runOnlyForDeploymentPostprocessing=0)

project_id, host_id = uid("project"), uid("host")
targets, products, references = [], [], []
for key, name, filename, kind in [
    ("host", "CompatibilityHarnessHost", "HarnessHost.m", "application"),
    ("ui", "LegacyRuntimeTests", "OldRuntimeAppTests.m", "bundle.ui-testing"),
]:
    app = key == "host"
    ref = add(key + "File", "PBXFileReference", lastKnownFileType="sourcecode.c.objc", path=filename, sourceTree="<group>")
    references.append(ref)
    source = add(key + "Build", "PBXBuildFile", fileRef=ref)
    product = add(key + "Product", "PBXFileReference", explicitFileType="wrapper.application" if app else "wrapper.cfbundle", includeInIndex=0, path=name + (".app" if app else ".xctest"), sourceTree="BUILT_PRODUCTS_DIR")
    products.append(product)
    settings = {"PRODUCT_NAME": "$(TARGET_NAME)", "PRODUCT_BUNDLE_IDENTIFIER": "test.cloud.compatibility." + name, "GENERATE_INFOPLIST_FILE": "YES", "IPHONEOS_DEPLOYMENT_TARGET": "15.0", "TARGETED_DEVICE_FAMILY": "1,2", "LD_RUNPATH_SEARCH_PATHS": "$(inherited) @executable_path/Frameworks @loader_path/Frameworks", "CODE_SIGNING_ALLOWED": "NO"}
    dependencies = []
    if app:
        settings.update(INFOPLIST_KEY_UILaunchScreen_Generation="YES", INFOPLIST_KEY_UIApplicationSceneManifest_Generation="NO", INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone="UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight", INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad="UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight")
    else:
        settings["TEST_TARGET_NAME"] = "CompatibilityHarnessHost"
        proxy = add("uiProxy", "PBXContainerItemProxy", containerPortal=project_id, proxyType=1, remoteGlobalIDString=host_id, remoteInfo="CompatibilityHarnessHost")
        dependencies.append(add("uiDependency", "PBXTargetDependency", target=host_id, targetProxy=proxy))
    targets.append(add(key, "PBXNativeTarget", name=name, productName=name, productReference=product, productType="com.apple.product-type." + kind, buildConfigurationList=configs(key, settings), buildPhases=[phase(key + "Sources", "Sources", [source]), phase(key + "Frameworks", "Frameworks", []), phase(key + "Resources", "Resources", [])], buildRules=[], dependencies=dependencies))
product_group = add("products", "PBXGroup", children=products, name="Products", sourceTree="<group>")
main = add("main", "PBXGroup", children=references + [product_group], sourceTree="<group>")
add("project", "PBXProject", attributes={"LastUpgradeCheck": "2660", "TargetAttributes": {uid("ui"): {"TestTargetID": host_id}}}, buildConfigurationList=configs("project", {"CLANG_ENABLE_MODULES": "YES", "CLANG_ENABLE_OBJC_ARC": "YES", "GCC_C_LANGUAGE_STANDARD": "gnu11", "SDKROOT": "iphoneos", "SUPPORTED_PLATFORMS": "iphonesimulator", "IPHONEOS_DEPLOYMENT_TARGET": "15.0", "ENABLE_USER_SCRIPT_SANDBOXING": "YES", "GCC_WARN_ABOUT_RETURN_TYPE": "YES_ERROR", "CLANG_WARN_OBJC_ROOT_CLASS": "YES_ERROR"}), compatibilityVersion="Xcode 14.0", developmentRegion="en", knownRegions=["en"], mainGroup=main, productRefGroup=product_group, projectDirPath="", projectRoot="", targets=targets)
def emit(value):
    if isinstance(value, dict): return "{\n" + "".join(json.dumps(str(k)) + " = " + emit(v) + ";\n" for k, v in value.items()) + "}"
    if isinstance(value, list): return "(" + ",".join(emit(v) for v in value) + ")"
    if isinstance(value, int): return str(value)
    return json.dumps(value)
project = root / "LegacyRuntime.xcodeproj"
project.mkdir(exist_ok=True)
(project / "project.pbxproj").write_text("// !$*UTF8*$!\n" + emit({"archiveVersion": 1, "classes": {}, "objectVersion": 56, "objects": objects, "rootObject": project_id}) + "\n")
def ref(key, name):
    return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{uid(key)}" BuildableName="{name}" BlueprintName="{name.split(".")[0]}" ReferencedContainer="container:LegacyRuntime.xcodeproj"/>'
scheme = project / "xcshareddata/xcschemes/LegacyRuntime.xcscheme"
scheme.parent.mkdir(parents=True, exist_ok=True)
scheme.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2660" version="1.7">
<BuildAction parallelizeBuildables="NO" buildImplicitDependencies="YES"><BuildActionEntries>
<BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{ref('host', 'CompatibilityHarnessHost.app')}</BuildActionEntry>
<BuildActionEntry buildForTesting="YES" buildForRunning="NO" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{ref('ui', 'LegacyRuntimeTests.xctest')}</BuildActionEntry>
</BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO">{ref('ui', 'LegacyRuntimeTests.xctest')}</TestableReference></Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="NO"><BuildableProductRunnable runnableDebuggingMode="0">{ref('host', 'CompatibilityHarnessHost.app')}</BuildableProductRunnable></LaunchAction>
<AnalyzeAction buildConfiguration="Debug"/>
</Scheme>
''')
