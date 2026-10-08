"""Read-only checks for declared source icons and actual built iPad payloads."""
import hashlib
import json
from pathlib import Path
import plistlib
import re
import struct
import zlib

SOURCE_SHA256 = 'dc2c12171d08a7d5cc51a66dc212601deccca7ab0d8d6d3c315d0da2ffa403d4'
CATALOG = Path('QRCatcher/Images.xcassets/AppIcon.appiconset')
IPAD = {'ipad-20x20@1x.png':20, 'ipad-20x20@2x.png':40, 'ipad-29x29@1x.png':29,
        'ipad-29x29@2x.png':58, 'ipad-40x40@1x.png':40, 'ipad-40x40@2x.png':80,
        'ipad-76x76@1x.png':76, 'ipad-76x76@2x.png':152, 'ipad-83.5x83.5@2x.png':167}

def require(value, reason):
    if not value: raise ValueError(reason)

def read(path, limit=4*1024*1024):
    path=Path(path)
    require(path.is_file() and not path.is_symlink() and path.resolve()==path.absolute(), 'unsafe or missing icon input: '+str(path))
    require(0 < path.stat().st_size <= limit, 'icon input byte limit')
    raw=path.read_bytes(); require(len(raw)<=limit, 'icon input changed size')
    return raw

def png(raw):
    require(raw[:8]==b'\x89PNG\r\n\x1a\n', 'not a PNG')
    offset=8; header=None; chunks=[]
    while offset < len(raw):
        require(offset+12<=len(raw), 'truncated PNG')
        size=struct.unpack_from('>I',raw,offset)[0]; kind=raw[offset+4:offset+8]
        require(size<=4*1024*1024 and offset+12+size<=len(raw), 'PNG chunk limit')
        data=raw[offset+8:offset+8+size]
        require(zlib.crc32(kind+data)&0xffffffff==struct.unpack_from('>I',raw,offset+8+size)[0], 'PNG CRC mismatch')
        chunks.append(kind.decode('ascii'))
        if kind==b'IHDR':
            require(header is None and len(data)==13, 'invalid PNG header')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            require(0<width<=4096 and 0<height<=4096 and depth==8 and color in (2,6)
                    and compression==filtering==0 and interlace==0, 'unsupported icon PNG')
            header={'width':width,'height':height,'bit_depth':depth,'color_type':color}
        offset+=12+size
        if kind==b'IEND': break
    require(header is not None and chunks.count('IHDR')==1 and chunks[-1]=='IEND'
            and 'IDAT' in chunks and offset==len(raw), 'incomplete PNG')
    return {**header,'chunks':chunks,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def source_icons(root):
    root=Path(root).resolve(); folder=root/CATALOG
    manifest=json.loads(read(root/'scripts/ipad_icon_manifest.json',16384))
    require(manifest['source_sha256']==SOURCE_SHA256 and manifest['pillow_version']=='12.3.0'
            and manifest['resampling']=='LANCZOS' and manifest['source_mode']=='RGB'
            and manifest['color_profile']=='sRGB intent 0', 'wrong icon derivation recipe')
    require(hashlib.sha256(read(folder/'marketing1024.png')).hexdigest()==SOURCE_SHA256, 'original artwork changed')
    pins={x['filename']:x for x in manifest['outputs']}
    require(len(manifest['outputs'])==len(pins)==9 and set(pins)==set(IPAD), 'incomplete committed iPad icon manifest')
    entries=json.loads(read(folder/'Contents.json',16384))['images']; found={}; result=[]
    for entry in entries:
        name=entry.get('filename'); require(isinstance(name,str) and Path(name).name==name and name.endswith('.png'), 'invalid declared icon filename')
        expected=round(float(entry['size'].split('x')[0])*int(entry['scale'][0]))
        value=png(read(folder/name))
        require([value['width'],value['height']]==[expected,expected], 'declared icon dimensions differ: '+name)
        if entry['idiom']=='ipad':
            require(name not in found and IPAD.get(name)==expected, 'unexpected iPad icon declaration')
            require(value['color_type']==2 and value['chunks']==['IHDR','sRGB','IDAT','IEND'], 'iPad icons must be opaque RGB with only sRGB metadata')
            require(value['sha256']==pins[name]['sha256'] and value['bytes']==pins[name]['bytes'], 'committed iPad icon differs: '+name)
            found[name]=expected
        result.append({'filename':name,'idiom':entry['idiom'],**value})
    require(found==IPAD, 'missing declared iPad icon')
    return {'original_artwork_sha256':SOURCE_SHA256,'declared_images':result,'ipad_images':9,'checked_in_assets_required':True}

def built_observation(app):
    app=Path(app).absolute()
    require(app.is_dir() and not app.is_symlink() and app.resolve()==app, 'unsafe built app path')
    info=plistlib.loads(read(app/'Info.plist',128*1024))
    files=sorted(app.glob('*.png')); require(len(files)<=64, 'too many loose icon candidates')
    return {'info':info,'loose_pngs':[{'filename':p.name,**png(read(p))} for p in files],
            'assets_car_sha256':hashlib.sha256(read(app/'Assets.car',16*1024*1024)).hexdigest()}

def built_icons(app, car_rows, observation=None):
    observation=built_observation(app) if observation is None else observation
    info=observation['info']
    require(info.get('CFBundleIdentifier')=='100mango.QRCatcher' and info.get('CFBundleExecutable')=='QRCatcher', 'wrong built app')
    require(info.get('CFBundleShortVersionString')=='1.1' and info.get('CFBundleVersion')=='3', 'expected iOS 1.1 build 3')
    family=info.get('UIDeviceFamily')
    require(family==[1,2] and all(type(x) is int for x in family) and info.get('DTPlatformName')=='iphoneos', 'expected iPhone/iPad device app')
    primary=info.get('CFBundleIcons~ipad',{}).get('CFBundlePrimaryIcon',{})
    refs=primary.get('CFBundleIconFiles')
    require(primary.get('CFBundleIconName')=='AppIcon' and isinstance(refs,list) and refs
            and all(isinstance(x,str) and Path(x).name==x and x not in ('.','..') for x in refs), 'missing built iPad icon file references')
    records=[]; referenced=set()
    for record in observation['loose_pngs']:
        matches=[ref for ref in refs if re.fullmatch(re.escape(ref.removesuffix('.png'))+r'(?:@[123]x)?(?:~ipad)?\.png',record['filename'])]
        if matches:referenced.update(matches)
        records.append({'references':matches,**record})
    require(referenced==set(refs), 'built iPad reference has no actual PNG')
    for size in (152,167):
        require(any(x['width']==x['height']==size and x['references'] for x in records),
                'missing referenced actual '+str(size)+'x'+str(size)+' iPad icon')
    require(isinstance(car_rows,list) and len(car_rows)<=4096, 'invalid Assets.car inventory')
    car_icons=[]
    for row in car_rows:
        if not isinstance(row,dict):continue
        rendition=row.get('RenditionName',''); name=row.get('Name',''); idiom=str(row.get('Idiom','')).lower()
        if rendition in IPAD or (isinstance(name,str) and name.startswith('AppIcon') and idiom in ('pad','ipad')):car_icons.append(row)
    observed={x['width'] for x in records if x['width']==x['height'] and x['references']}
    observed.update(x['PixelWidth'] for x in car_icons if type(x.get('PixelWidth')) is int and x.get('PixelHeight')==x['PixelWidth'])
    return {'bundle':'100mango.QRCatcher','version':'1.1','build':'3','device_family':[1,2],
            'ipad_primary_icon':primary,'loose_pngs':records,'car_ipad_icon_renditions':car_icons,
            'observed_ipad_dimensions':sorted(observed),'required_referenced_png_dimensions':[152,167],
            'source_76_icon_checked_separately':True,
            'assets_car_sha256':observation['assets_car_sha256']}
