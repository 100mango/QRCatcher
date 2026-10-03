#!/usr/bin/env python3
"""Derive standard macOS icon sizes from the unchanged retained app artwork.
No artwork redesign, network, third-party package or signing resource is involved.
Uses Apple's local sips in the cloud Mac build environment.
"""
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
source=root/'QRCatcher/Images.xcassets/AppIcon.appiconset/marketing1024.png'
expected='dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4'
assert hashlib.sha256(source.read_bytes()).hexdigest()==expected,'Retained artwork changed; review it before rebuilding icons'
folder=root/'QRCatcherMac/Assets.xcassets/AppIcon.appiconset'
for image in json.loads((folder/'Contents.json').read_text())['images']:
 size=int(image['size'].split('x')[0])*int(image['scale'][0])
 destination=folder/image['filename']
 subprocess.run(['sips','-s','format','png','--resampleHeightWidth',str(size),str(size),str(source),'--out',str(destination)],check=True,stdout=subprocess.DEVNULL)
 print(image['filename'],size,hashlib.sha256(destination.read_bytes()).hexdigest())
