"""Private price-safe PNG quotation rendering.

Only explicit user selling prices are passed in via effective_usd; source raw_usd
must NEVER be considered as a fallback, including scheduled Telegram images.
"""
from datetime import datetime
from pathlib import Path
import re

PERIOD_NAMES={'24h':'24h预估销量','7d':'7天预估销量','30d':'30天预估销量'}

def prepare_public_items(records, include_oos=True):
    published=[]
    for r in records:
        if not include_oos and (r['stock'] is None or r['stock']<=0):continue
        price=r['effective_usd'] if 'effective_usd' in r.keys() else None
        if price is None or str(price).strip()=='':
            raise ValueError('项目含有未设置自定义售价的商品，已阻止截图/发布（绝不使用网站原价）')
        name=r['effective_name'] if 'effective_name' in r.keys() else None
        if not name:raise ValueError('商品缺少展示名称')
        published.append({'id':r['id'],'name':name,'price':str(price),'stock':r['stock'],
                          'variant':r['variant'] if 'variant' in r.keys() else ''})
    return published

def render_project(records,project_name,dest_dir,title='每日商品报价',footer='库存及销量仅为采集观察数据',
                   include_oos=True,sales_periods=(),sales_by_product=None):
    from PIL import Image, ImageDraw, ImageFont
    items=prepare_public_items(records,include_oos)
    if not items:raise ValueError('项目没有符合展示条件的商品')
    periods=tuple(k for k in sales_periods if k in PERIOD_NAMES)
    sales_by_product=sales_by_product or {}
    dest=Path(dest_dir)/re.sub(r'[\\/:*?"<>|]','_',project_name);dest.mkdir(parents=True,exist_ok=True)
    def font(sz,bold=False):
        for path in ([r'C:\Windows\Fonts\msyhbd.ttc',r'C:\Windows\Fonts\msyh.ttc'] if bold else [r'C:\Windows\Fonts\msyh.ttc']):
            try:return ImageFont.truetype(path,sz)
            except OSError:pass
        for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
            try:return ImageFont.truetype(path,sz)
            except OSError:pass
        return ImageFont.load_default()
    out=[];row_height=82 if periods else 49
    for offset in range(0,len(items),18):
        chunk=items[offset:offset+18];h=220+len(chunk)*row_height
        img=Image.new('RGB',(1100,h),'#f8fbff');d=ImageDraw.Draw(img)
        d.rectangle((0,0,1100,112),fill='#e6f0ff')
        d.rectangle((0,0,1100,8),fill='#1767ff')
        d.text((36,25),title[:45],font=font(34,True),fill='#16335b')
        d.text((36,90),'商品名称',font=font(19,True),fill='#425c78')
        d.text((780,90),'自定义售价 USD',font=font(19,True),fill='#425c78')
        d.text((990,90),'库存',font=font(19,True),fill='#425c78')
        d.line((30,128,1070,128),fill='#bdd4f4',width=2)
        for i,r in enumerate(chunk):
            y=144+i*row_height
            d.text((36,y),(r['name']+' '+(r['variant'] or ''))[:43],font=font(19),fill='#1e314c')
            d.text((790,y),'$'+r['price'],font=font(20,True),fill='#1262e9')
            d.text((994,y),str(r['stock']) if r['stock'] is not None else '?',font=font(19),fill='#178257')
            if periods:
                stats=sales_by_product.get(r['id'],{})
                summary='     '.join(PERIOD_NAMES[k]+': '+(str(stats.get(k)) if stats.get(k) is not None else '数据不足') for k in periods)
                d.text((36,y+36),summary[:100],font=font(15),fill='#60718a')
            d.line((30,y+row_height-12,1070,y+row_height-12),fill='#e2eaf7')
        d.text((36,h-50),footer[:75],font=font(17),fill='#59718e')
        filename=f'{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}_{offset//18+1}.png'
        path=dest/filename;img.save(path);out.append(path)
    return out
