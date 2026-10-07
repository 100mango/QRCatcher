#!/usr/bin/env python3
"""Local-only mechanical Top Shelf 2x outputs from the retained 1024px raster.

The native archive route keeps the existing Swift generator for every existing
TV 1x and Small 2x image. This helper writes only the two added PNGs. Pillow's
LANCZOS interpolation is not CoreGraphics byte equivalence and adds no detail.
"""
from pathlib import Path
import hashlib
import json
import sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE='QRCatcher/Images.xcassets/AppIcon.appiconset/marketing1024.png'
SOURCE_SHA256='dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4'
CATALOG='QRCatcherTV/Assets.xcassets/AppIcon.brandassets'
SLOTS={'TopShelf.imageset':(3840,1440),'TopShelfWide.imageset':(4640,1440)}
def need(ok,message):
    if not ok:raise ValueError(message)
def source(root=ROOT):
    raw=(root/SOURCE).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==SOURCE_SHA256,'Original artwork changed')
    image=Image.open(root/SOURCE);image.load()
    need(image.size==(1024,1024) and image.mode=='RGB','Unexpected source raster')
    return image

def render(image,size):
    width,height=size
    # Existing Swift recipe uses a centered square and CGColor(gray:0.08).
    # 8-bit mechanical counterpart is RGB(20,20,20), matching its geometry.
    result=Image.new('RGB',size,(20,20,20))
    result.paste(image.resize((height,height),Image.Resampling.LANCZOS),((width-height)//2,0))
    return result

def verify(root=ROOT):
    original=source(root);rows=[]
    for slot,size in SLOTS.items():
        directory=root/CATALOG/slot
        spec=json.loads((directory/'Contents.json').read_text())
        need(spec['images']==[{'filename':'Icon.png','idiom':'tv','scale':'1x'},{'filename':'Icon-2x.png','idiom':'tv','scale':'2x'}],'Unexpected Top Shelf scale mapping')
        path=directory/'Icon-2x.png'
        with Image.open(path) as actual:
            expected=render(original,size)
            need(actual.size==size and actual.mode=='RGB' and actual.tobytes()==expected.tobytes(),'Incorrect mechanical Top Shelf pixels')
        data=path.read_bytes();rows.append({'path':path.relative_to(root).as_posix(),'dimensions':list(size),'mode':'RGB','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'artwork_rectangle':[(size[0]-1440)//2,0,1440,1440]})
    return {'source':SOURCE,'source_sha256':SOURCE_SHA256,'source_dimensions':[1024,1024],
      'vector_source_available':False,'method':'Pillow LANCZOS, centered 1440px square on RGB20 background',
      'source_enlargement':1.40625,'new_detail_created':False,'coregraphics_pixel_equivalence_claimed':False,
      'existing_small_2x_or_1x_files_rewritten':False,'assets':rows}

def materialize(root=ROOT):
    original=source(root)
    for slot,size in SLOTS.items():render(original,size).save(root/CATALOG/slot/'Icon-2x.png','PNG')
    return verify(root)
if __name__=='__main__':
    need(sys.argv[1:] in ([],['--check']),'Only --check is supported')
    print(json.dumps(verify() if sys.argv[1:] else materialize(),indent=2))
