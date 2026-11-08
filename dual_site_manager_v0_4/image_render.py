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
        img=Image.new('RGB',(1100,h),'#111c2b');d=ImageDraw.Draw(img)
        d.text((36,25),title[:45],font=font(34,True),fill='#ffffff')
        d.text((36,90),'商品名称',font=font(19,True),fill='#aabbd0')
        d.text((780,90),'售价 USD',font=font(19,True),fill='#aabbd0')
        d.text((990,90),'库存',font=font(19,True),fill='#aabbd0')
        d.line((30,128,1070,128),fill='#45627e',width=2)
        for i,r in enumerate(chunk):
            y=144+i*49
            d.text((36,y),(r['name']+' '+(r['variant'] or ''))[:47],font=font(19),fill='#edf2f7')
            d.text((790,y),'$'+(r['custom_usd'] or r['raw_usd']),font=font(20,True),fill='#f8d28c')
            d.text((994,y),str(r['stock']) if r['stock'] is not None else '?',font=font(19),fill='#92dec0')
            d.line((30,y+37,1070,y+37),fill='#2e4257')
        d.text((36,h-50),footer[:75],font=font(17),fill='#b0c1d0')
        filename=f'{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}_{offset//18+1}.png'
        path=dest/filename;img.save(path);out.append(path)
    return out
