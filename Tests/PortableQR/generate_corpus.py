from pathlib import Path
import json,base64,hashlib,struct,random
from PIL import Image,ImageDraw,ImageOps
from reportlab.graphics.barcode.qrencoder import QRCode,QRECI,QR8bitByte
root=Path(__file__).resolve().parents[2];out=root/'build/PortableQREvaluation/corpus';out.mkdir(parents=True,exist_ok=True);fixture=root/'Tests/Fixtures';rows=[]
def save(name,im,expected):
 im=im.convert('L');assert max(im.size)<=1536
 data=struct.pack('<II',*im.size)+im.tobytes();(out/(name+'.gray')).write_bytes(data)
 rows.append({'name':name+'.gray','bytes':len(data),'dimensions':im.size,'sha256':hashlib.sha256(data).hexdigest(),'expected':expected})
def qr(segments):
 q=QRCode(None,1)
 for s in segments:q.addData(s)
 q.make();n=q.getModuleCount();im=Image.new('L',((n+8)*8,)*2,255);draw=ImageDraw.Draw(im)
 for y,row in enumerate(q.modules):
  for x,on in enumerate(row):
   if on:draw.rectangle(((x+4)*8,(y+4)*8,(x+5)*8-1,(y+5)*8-1),fill=0)
 return im
for item in json.loads((fixture/'manifest.json').read_text()):
 if 'expected_error' in item or item['name'].startswith('eci-'):continue
 path=fixture/item['name'];path.write_bytes(base64.b64decode(path.with_suffix('.png.base64').read_text()));assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
 save(path.stem,Image.open(path),item['payloads'])
for name,segments,expected in [
 ('eci-utf8',[QRECI(26),QR8bitByte('你好 🌈'.encode())],['你好 🌈']),
 ('eci-latin1',[QRECI(3),QR8bitByte('Café'.encode('latin1'))],['Café']),
 ('eci-shiftjis',[QRECI(20),QR8bitByte('日本語'.encode('shift_jis'))],['日本語']),
 ('eci-mixed',[QRECI(3),QR8bitByte('Café'.encode('latin1')),QRECI(26),QR8bitByte(' 你好'.encode())],['Café 你好'])]:
 im=qr(segments);im.save(out/(name+'.png'));save(name,im,expected)
u=Image.open(fixture/'unicode.png');save('mirrored',ImageOps.mirror(u),['QRCatcher 你好 🌈 123']);save('inverted',ImageOps.invert(u),['QRCatcher 你好 🌈 123'])
save('cropped',u.crop((u.width//3,0,u.width,u.height)),None)
rng=random.Random(1739)
for i in range(24):
 w,h=rng.randrange(1,256),rng.randrange(1,256)
 save(f'noise-{i}',Image.frombytes('L',(w,h),bytes(rng.randrange(256) for _ in range(w*h))),None)
for name,data in [('empty',b''),('truncated-header',b'\x00\xff\xff'),('truncated-raster',struct.pack('<II',100,100)+b'\x00'*17),('overflow-dimensions',struct.pack('<II',0xffffffff,0xffffffff)),('zero-dimension',struct.pack('<II',0,300))]:
 (out/(name+'.gray')).write_bytes(data);rows.append({'name':name+'.gray','bytes':len(data),'expected_rejection':True,'sha256':hashlib.sha256(data).hexdigest()})
save('maximum-1536',u.resize((1536,1536),Image.Resampling.NEAREST),['QRCatcher 你好 🌈 123'])
for count in [32,33]:
 mosaic=Image.new('L',(900,900),255)
 for i in range(count):
  code=qr([QR8bitByte(('LIMIT-'+str(i)).encode())]).resize((120,120),Image.Resampling.NEAREST)
  mosaic.paste(code,((i%6)*150,(i//6)*150))
 save('symbols-'+str(count),mosaic,['LIMIT-'+str(i) for i in range(count)] if count==32 else None)
 if count==33:rows[-1]['expected_limit_rejection']=True
(out/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(len(rows),'bounded corpus cases')
