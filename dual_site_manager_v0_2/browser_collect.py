"""Optional Playwright browser collector, with ordinary modal handling and guarded parsing.

No CAPTCHA bypass or automatic login. Browser retains a separate profile for each website.
"""
import json
import re
import time
from datetime import datetime
from decimal import Decimal
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

ALLOWED = {'FB1314': {'fb1314.com', 'www.fb1314.com'},
           'CEOACC': {'ceoacc.com', 'www.ceoacc.com'}}


def validate_link(source, url):
    if source not in ALLOWED:
        raise ValueError('未知采集来源')
    u = urlparse(url.strip())
    if u.scheme != 'https' or u.hostname not in ALLOWED[source] or u.username or u.password:
        raise ValueError('仅支持对应网站的 HTTPS 页面链接')
    return url.strip()


def modal_action(source, labels):
    """Pure selector decision, safe to unit test without accessing either website."""
    if source == 'FB1314':
        for label in labels:
            if label.strip().casefold() in ('继续 continue', 'continue', '继续'):
                return label
    if source == 'CEOACC':
        for preferred in ('不再显示', '关闭'):
            for label in labels:
                if label.strip() == preferred:
                    return label
    return None


def dismiss_site_popup(page, source):
    """Click ONLY exact text matched in known UI; never click purchase/checkout widgets."""
    candidates = ['继续 Continue', 'Continue', '继续'] if source == 'FB1314' else ['不再显示', '关闭']
    for target in candidates:
        for loc in [page.get_by_role('button', name=target, exact=True),
                    page.get_by_text(target, exact=True)]:
            try:
                if loc.count() == 1 and loc.is_visible(timeout=1200):
                    loc.click(timeout=4000)
                    page.wait_for_timeout(400)
                    return target
            except Exception:
                continue
    return None


def extract_fb(text, url):
    """FB1314 detail page only; refuse unclear prices and empty stock."""
    path = urlparse(url).path
    m = re.search(r'^/goods/(\d+)\.html$', path)
    if not m:
        raise ValueError('FB1314 商品详情链接应为 /goods/数字.html')
    lines = [re.sub(r'\s+', ' ', v).strip() for v in text.splitlines() if v.strip()]
    clean = '\n'.join(lines)
    stock = re.search(r'库存\s*[:：]?\s*(\d+)', clean)
    # Locate first USD amount after stock indicator to avoid sidebar or suggested goods prices.
    price = re.search(r'\$\s*(\d+(?:\.\d{1,4})?)', clean[stock.end():stock.end()+300]) if stock else None
    if not stock or not price:
        raise ValueError('未在商品详情定位到明确库存与 USD 价格')
    # Main heading supplied separately in browser_collect, never guess from body.
    return {'source':'FB1314','external_id':m.group(1),'stock':int(stock.group(1)),
            'price':str(Decimal(price.group(1))),'url':url}


def extract_ceo_from_jsonld(blocks, url):
    """Only use semantically labeled Product JSON-LD with explicit USD and available stock count.

    Without an actual inventory count, refuse import instead of interpreting availability as count.
    """
    found = []
    for block in blocks:
        try: data = json.loads(block)
        except (ValueError, TypeError): continue
        queue = data if isinstance(data,list) else [data]
        while queue:
            item = queue.pop(0)
            if not isinstance(item,dict): continue
            queue.extend(v for v in item.get('@graph',[]) if isinstance(v,dict))
            if 'Product' not in (item.get('@type') if isinstance(item.get('@type'),list) else [item.get('@type')]):
                continue
            offers = item.get('offers',{})
            if isinstance(offers,list): offers = offers[0] if len(offers)==1 else {}
            if not isinstance(offers,dict):continue
            currency = offers.get('priceCurrency')
            quantity = offers.get('inventoryLevel')
            if isinstance(quantity,dict): quantity=quantity.get('value')
            if currency!='USD' or quantity is None or not str(quantity).isdigit():continue
            name=item.get('name'); price=offers.get('price')
            external_id=item.get('sku') or item.get('productID')
            if not name or price is None or not external_id:continue
            found.append({'source':'CEOACC','external_id':str(external_id),'name':str(name),
                          'price':str(Decimal(str(price))),'stock':int(quantity),'url':url})
    if len(found) != 1:
        raise ValueError('CEOACC 页面缺少唯一且完整的 USD 商品结构化数据（名称、ID、价格、库存），已跳过写入')
    return found[0]


def browse_and_collect(source, urls, profiles_dir, diagnosis_dir, headed=True):
    """Browser visits user-provided public product URLs; return (items, errors, events).

    Browser opens visibly by default to permit manual interaction with login/security prompts.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError('请先安装 playwright 并执行 python -m playwright install chromium') from e
    profile=Path(profiles_dir)/source.lower()
    diagnostic=Path(diagnosis_dir)/source.lower()
    profile.mkdir(parents=True, exist_ok=True)
    diagnostic.mkdir(parents=True, exist_ok=True)
    items,errors,events=[],[],[]
    with sync_playwright() as p:
        browser=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=not headed,
             viewport={'width':1280,'height':900},locale='zh-CN',accept_downloads=False)
        try:
            page=browser.pages[0] if browser.pages else browser.new_page()
            for url in urls:
                try:
                    validate_link(source,url)
                    page.goto(url,wait_until='domcontentloaded',timeout=30000)
                    page.wait_for_timeout(900)
                    clicked=dismiss_site_popup(page,source)
                    events.append(f'{source} {url}：'+(f'关闭弹窗 [{clicked}]' if clicked else '未检测到已知弹窗'))
                    title=page.title()
                    if re.search(r'captcha|cloudflare|verify you are human|验证您是人类|安全验证',title,re.I):
                        raise ValueError('检测到安全验证，需人工操作；未自动绕过')
                    if source=='FB1314':
                        text=page.locator('body').inner_text(timeout=10000)
                        record=extract_fb(text,url)
                        # Strongly prefer product main heading; falls back to no write.
                        heading=page.locator('h1').first
                        name=heading.inner_text(timeout=3000).strip() if heading.count() else ''
                        if not name: raise ValueError('商品主标题缺失')
                        record['name']=name
                    else:
                        blocks=page.locator('script[type="application/ld+json"]').all_text_contents()
                        record=extract_ceo_from_jsonld(blocks,url)
                    items.append(record)
                except Exception as e:
                    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    screenshot=diagnostic/(stamp+'.png')
                    try:page.screenshot(path=str(screenshot),full_page=False,timeout=5000)
                    except Exception: screenshot=None
                    errors.append(f'{source} {url}：{e}'+(f' [诊断截图 {screenshot}]' if screenshot else ''))
                time.sleep(1.2)
        finally:
            browser.close()
    return items,errors,events
