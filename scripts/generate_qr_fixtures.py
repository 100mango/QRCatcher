#!/usr/bin/env python3
"""Independent QR golden matrices: ReportLab's encoder, never the Apple production codec.
Only regenerate intentionally. PNG bytes are checked in as base64 to preserve the
text-only GitHub tree transport; fixture materialization verifies exact SHA-256.
"""
import base64,hashlib,json,pathlib
from reportlab.graphics.barcode.qrencoder import QRCode
from PIL import Image,ImageDraw
root=pathlib.Path(__file__).resolve().parents[1]/'Tests/Fixtures'
def qr(payload):
 q=QRCode(None,1);q.addData(payload);q.make();n=q.getModuleCount();im=Image.new('RGB',((n+8)*8,)*2,'white');d=ImageDraw.Draw(im)
 for y,row in enumerate(q.modules):
  for x,v in enumerate(row):
   if v:d.rectangle(((x+4)*8,(y+4)*8,(x+5)*8-1,(y+5)*8-1),fill='black')
 return im
ascii='https://example.com/qrcatcher?source=golden'
unicode='QRCatcher 你好 🌈 123'
a=qr(ascii);u=qr(unicode)
m=Image.new('RGB',(a.width+u.width+80,max(a.height,u.height)+80),'white');m.paste(a,(20,40));m.paste(u,(a.width+60,40))
items=[('ascii',a,[ascii]),('unicode',u,[unicode]),('rotated',u.rotate(90,expand=True),[unicode]),('invalid',Image.new('RGB',(256,256),'white'),[]),('multiple',m,[ascii,unicode])]
manifest=[]
import io
for name,im,payloads in items:
 b=io.BytesIO();im.save(b,format='PNG');data=b.getvalue();(root/(name+'.png.base64')).write_text(base64.b64encode(data).decode()+'\n');manifest.append(dict(name=name+'.png',sha256=hashlib.sha256(data).hexdigest(),payloads=payloads))
(root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
