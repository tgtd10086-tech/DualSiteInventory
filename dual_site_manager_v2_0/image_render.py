"""Render the approved minimal blue/white four-column quotation table."""
from datetime import datetime
from pathlib import Path
import re

PERIOD_NAMES={'24h':'本日销量','7d':'本周销量','30d':'本月销量'}

def prepare_public_items(records, include_oos=True):
    published=[]
    for r in records:
        if 'status' in r.keys() and r['status']=='excluded':
            continue
        if 'include_in_capture' in r.keys() and not r['include_in_capture']:
            continue
        if not include_oos and (r['stock'] is None or r['stock']<=0):
            continue
        price=r['effective_usd'] if 'effective_usd' in r.keys() else None
        if price is None or str(price).strip()=='':
            # Hidden items may be excluded, but a visible item without a custom price is never published.
            raise ValueError('项目含有未设置销售价的可见商品，已阻止截图/发布（绝不使用网站原价）')
        name=r['effective_name'] if 'effective_name' in r.keys() else None
        if not name:raise ValueError('商品缺少展示名称')
        published.append({'id':r['id'],'name':name,'price':str(price),'stock':r['stock'],
                          'variant':r['variant'] if 'variant' in r.keys() else ''})
    return published

def render_project(records,project_name,dest_dir,title='黑盒铺子',footer='销量根据库存变化估算，仅供参考',
                   include_oos=True,sales_periods=('24h',),sales_by_product=None):
    from PIL import Image, ImageDraw, ImageFont
    items=prepare_public_items(records,include_oos)
    if not items:raise ValueError('项目没有符合展示条件的商品')
    periods=tuple(k for k in sales_periods if k in PERIOD_NAMES)
    if len(periods)!=1:raise ValueError('截图必须且只能选择一种销量周期')
    period=periods[0]; sales_by_product=sales_by_product or {}
    dest=Path(dest_dir)/re.sub(r'[\\/:*?"<>|]','_',project_name);dest.mkdir(parents=True,exist_ok=True)
    def font(sz,bold=False):
        paths=([r'C:\Windows\Fonts\msyhbd.ttc',r'C:\Windows\Fonts\msyh.ttc'] if bold else [r'C:\Windows\Fonts\msyh.ttc'])
        for path in paths:
            try:return ImageFont.truetype(path,sz)
            except OSError:pass
        for path in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
            try:return ImageFont.truetype(path,sz)
            except OSError:pass
        return ImageFont.load_default()
    def wrap(text,max_chars=30):
        text=str(text);return [text[i:i+max_chars] for i in range(0,len(text),max_chars)] or ['']
    # Wider name column, one sales column only; 16 rows per image keeps text readable.
    out=[]; per_page=16; width=1240; header_h=190; row_h=66; bottom_h=78
    for offset in range(0,len(items),per_page):
        chunk=items[offset:offset+per_page]
        heights=[max(row_h,28*min(2,len(wrap(x['name']+' '+(x['variant'] or ''),38)))+22) for x in chunk]
        height=header_h+sum(heights)+bottom_h
        img=Image.new('RGB',(width,height),'#ffffff');d=ImageDraw.Draw(img)
        d.rectangle((0,0,width,14),fill='#1767ff');d.rectangle((0,14,width,header_h),fill='#eef5ff')
        d.text((42,38),'黑盒铺子',font=font(34,True),fill='#173b70')
        d.text((42,92),str(project_name)[:55],font=font(27,True),fill='#1e3d66')
        d.text((width-42,105),'更新时间：'+datetime.now().astimezone().strftime('%Y-%m-%d %H:%M'),font=font(16),fill='#526b88',anchor='ra')
        y=header_h
        # Columns: serial, name, price, stock, selected sales period.
        xs=[42,112,710,895,1055]
        d.rectangle((30,y,width-30,y+54),fill='#dceaff')
        headers=[('序号',xs[0]),('商品名称',xs[1]),('价格',xs[2]),('现货库存',xs[3]),(PERIOD_NAMES[period],xs[4])]
        for label,x in headers:d.text((x,y+14),label,font=font(18,True),fill='#24466e')
        y+=54
        for i,(item,rh) in enumerate(zip(chunk,heights),offset+1):
            d.rectangle((30,y,width-30,y+rh),fill='#f5f9ff' if i%2 else '#ffffff')
            d.text((xs[0],y+18),str(i),font=font(17),fill='#506783')
            lines=wrap(item['name']+' '+(item['variant'] or ''),38)[:2]
            for li,line in enumerate(lines):d.text((xs[1],y+10+li*27),line,font=font(17),fill='#263d59')
            d.text((xs[2],y+17),'$'+item['price'],font=font(18,True),fill='#1262d6')
            d.text((xs[3],y+17),str(item['stock']) if item['stock'] is not None else '—',font=font(18),fill='#245b48')
            stat=sales_by_product.get(item['id'],{}).get(period)
            d.text((xs[4],y+17),str(stat) if stat is not None else '—',font=font(18),fill='#245b48')
            d.line((30,y+rh,width-30,y+rh),fill='#dce6f3',width=1)
            y+=rh
        d.text((42,height-48),footer[:85],font=font(14),fill='#71839a')
        filename=f'{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}_{offset//per_page+1}.png'
        path=dest/filename;img.save(path);out.append(path)
    return out
