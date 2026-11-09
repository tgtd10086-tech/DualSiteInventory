"""Reusable non-screen PNG quotation renderer, safe for background jobs."""
from datetime import datetime
from pathlib import Path
import re

def render_project(records,project_name,dest_dir,title='每日商品报价',footer='报价以实时库存为准',include_oos=True):
    from PIL import Image, ImageDraw, ImageFont
    records=[r for r in records if include_oos or (r['stock'] is not None and r['stock']>0)]
    if not records:raise ValueError('项目没有符合展示条件的商品')
    dest=Path(dest_dir)/re.sub(r'[\\/:*?"<>|]','_',project_name);dest.mkdir(parents=True,exist_ok=True)
    def font(sz,bold=False):
        for p in ([r'C:\Windows\Fonts\msyhbd.ttc',r'C:\Windows\Fonts\msyh.ttc'] if bold else [r'C:\Windows\Fonts\msyh.ttc']):
            try:return ImageFont.truetype(p,sz)
            except OSError:pass
        return ImageFont.load_default()
    out=[]
    for offset in range(0,len(records),18):
        chunk=records[offset:offset+18];h=220+len(chunk)*49
        img=Image.new('RGB',(1100,h),'#f8fbff');d=ImageDraw.Draw(img)
        d.rectangle((0,0,1100,112),fill='#e6f0ff')
        d.rectangle((0,0,1100,8),fill='#1767ff')
        d.text((36,25),title[:45],font=font(34,True),fill='#16335b')
        d.text((36,90),'商品名称',font=font(19,True),fill='#425c78')
        d.text((780,90),'售价 USD',font=font(19,True),fill='#425c78')
        d.text((990,90),'库存',font=font(19,True),fill='#425c78')
        d.line((30,128,1070,128),fill='#bdd4f4',width=2)
        for i,r in enumerate(chunk):
            y=144+i*49
            d.text((36,y),((r['effective_name'] if 'effective_name' in r.keys() else (r['display_name'] or r['name']))+' '+(r['variant'] or ''))[:47],font=font(19),fill='#1e314c')
            d.text((790,y),'$'+(r['effective_usd'] if 'effective_usd' in r.keys() else (r['custom_usd'] or r['raw_usd'])),font=font(20,True),fill='#1262e9')
            d.text((994,y),str(r['stock']) if r['stock'] is not None else '?',font=font(19),fill='#178257')
            d.line((30,y+37,1070,y+37),fill='#e2eaf7')
        d.text((36,h-50),footer[:75],font=font(17),fill='#59718e')
        filename=f'{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}_{offset//18+1}.png'
        path=dest/filename;img.save(path);out.append(path)
    return out
