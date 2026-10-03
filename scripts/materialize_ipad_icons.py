#!/usr/bin/env python3
"""Materialize iPad icon sizes from the unchanged original QRCatcher artwork."""
import hashlib,json,pathlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
folder=root/'QRCatcher/Images.xcassets/AppIcon.appiconset';source=folder/'marketing1024.png'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4'
for image in json.loads((folder/'Contents.json').read_text())['images']:
 if image['idiom']!='ipad':continue
 size=round(float(image['size'].split('x')[0])*int(image['scale'][0]))
 subprocess.run(['sips','-s','format','png','--resampleHeightWidth',str(size),str(size),str(source),'--out',str(folder/image['filename'])],check=True,stdout=subprocess.DEVNULL)
 print(image['filename'],size)
