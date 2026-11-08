"""Bounded, respectful public-page discovery; does not defeat challenges or log in.

This finds linked publicly accessible catalogue pages, then extracts products. It
must never claim exhaustive coverage if pages are inaccessible or truncated.
"""
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
import re
import time
from browser_collect import ALLOWED, dismiss_site_popup, extract_fb, extract_ceo_from_jsonld

BLOCKED = re.compile(r'/(?:cart|checkout|pay|payment|order|login|register|logout|user|account|support|contact|privacy|terms|api|admin)(?:/|$)',re.I)
ASSET = re.compile(r'\.(?:css|js|png|jpe?g|webp|gif|svg|ico|pdf|zip|rar|exe|mp4)(?:$|\?)',re.I)
FB_DETAIL = re.compile(r'^/goods/\d+\.html$',re.I)
GENERIC_DETAIL = re.compile(r'/(?:goods|product|products|item|detail|shop)/[^/]+',re.I)
CATEGORY = re.compile(r'/(?:category|categories|catalog|shop|goods|product|products|list|search|sort|page)/?', re.I)
PAGE_PARAM = re.compile(r'(?:[?&](?:page|p|cursor|category|category_id|cat|sort)=)',re.I)

def canonical_url(source,href,base):
    target=urldefrag(urljoin(base,href))[0]
    parsed=urlparse(target)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED[source] or parsed.username or parsed.password:
        return None
    if BLOCKED.search(parsed.path) or ASSET.search(parsed.path):return None
    return target.rstrip('/') if parsed.path != '/' else target

def is_detail(source,url):
    path=urlparse(url).path
    return bool(FB_DETAIL.match(path) if source=='FB1314' else GENERIC_DETAIL.search(path))

def parse_product(page,source,url):
    if source=='FB1314':
        record=extract_fb(page.locator('body').inner_text(timeout=12000),url)
        heading=page.locator('h1').first
        name=heading.inner_text(timeout=3000).strip() if heading.count() else ''
        if not name:raise ValueError('缺少商品主标题')
        record['name']=name
        return record
    blocks=page.locator('script[type="application/ld+json"]').all_text_contents()
    try:return extract_ceo_from_jsonld(blocks,url)
    except ValueError:
        # Verified DOM fallback requires a named product, explicit USD amount, and numbered inventory.
        body=page.locator('body').inner_text(timeout=12000)
        heading=page.locator('h1').first
        name=heading.inner_text(timeout=3000).strip() if heading.count() else ''
        stock=re.search(r'(?:库存|存货|Stock|Inventory)\s*[:：]?\s*(\d+)',body,re.I)
        price=re.search(r'(?:USD\s*\$?\s*|\$\s*)(\d+(?:\.\d{1,4})?)',body)
        path=urlparse(url).path
        uid=path.rstrip('/').split('/')[-1]
        if not (name and stock and price and uid):
            raise ValueError('未能从 CEOACC 页面可靠提取商品名称、USD 价格和数字库存')
        return {'source':source,'external_id':uid,'name':name,'price':price.group(1),'stock':int(stock.group(1)),'url':url}

def scan_site(source,profiles_dir,diagnosis_dir,max_pages=1200,headed=True,stop=None,progress=None):
    """Site-wide link discovery with bounded crawling. Returns records, errors, stats.

    Stock/price never guessed; discovered links without valid detail are listed as errors.
    """
    from playwright.sync_api import sync_playwright
    root='https://fb1314.com/' if source=='FB1314' else 'https://ceoacc.com/'
    profile=Path(profiles_dir)/source.lower();profile.mkdir(parents=True,exist_ok=True)
    diag=Path(diagnosis_dir)/source.lower();diag.mkdir(parents=True,exist_ok=True)
    queue=deque([(root,0)]);queued={root};seen=set();products=[];errors=[]
    stats={'visited':0,'found_links':0,'parsed':0,'failed':0,'truncated':False,'source':source}
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=not headed,
           viewport={'width':1280,'height':900},locale='zh-CN',accept_downloads=False)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            while queue and stats['visited'] < max_pages:
                if stop and stop.is_set():break
                url,depth=queue.popleft();queued.discard(url)
                if url in seen:continue
                seen.add(url)
                try:
                    resp=page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    page.wait_for_timeout(400)
                    dismiss_site_popup(page,source)
                    if urlparse(page.url).hostname not in ALLOWED[source]:raise RuntimeError('网站跳转到非本站页面，已停止解析')
                    title=page.title()
                    if re.search(r'captcha|cloudflare|verify you are human|安全验证',title,re.I):
                        raise RuntimeError('遇到安全验证，请人工处理；不尝试绕过')
                    stats['visited']+=1
                    if is_detail(source,url):
                        try:
                            products.append(parse_product(page,source,url));stats['parsed']+=1
                        except Exception as exc:
                            errors.append(f'{url} 商品解析失败：{exc}');stats['failed']+=1
                    else:
                        for record in extract_catalog_cards(page,source,url):
                            products.append(record);stats['parsed']+=1
                    # Discover linked categories, pagination, and detail pages.
                    if depth < 6:
                        anchors=page.locator('a[href]').evaluate_all('(els) => els.map(e=>e.getAttribute("href"))')
                        for raw in anchors:
                            if not raw:continue
                            dest=canonical_url(source,raw,url)
                            if not dest or dest in seen:continue
                            path=urlparse(dest).path
                            if is_detail(source,dest):
                                if dest not in queued:queue.append((dest,depth+1));queued.add(dest)
                                stats['found_links']+=1
                            elif depth<4 and (dest==root or CATEGORY.search(path) or PAGE_PARAM.search(dest)):
                                if dest not in queued:queue.append((dest,depth+1));queued.add(dest)
                    if progress and stats['visited']%10==0:progress(dict(stats))
                    time.sleep(0.6)
                except Exception as exc:
                    stats['failed']+=1;errors.append(f'{url}: {exc}')
                    if len(errors)<=15:
                        try:page.screenshot(path=str(diag/f'error_{int(time.time()*1000)}.png'),timeout=5000)
                        except Exception:pass
            stats['truncated']=bool(queue) or bool(stop and stop.is_set())
        finally:context.close()
    stats['discovered_unique']=len(seen)+len(queue)
    if progress:progress(dict(stats))
    return products,errors,stats

def extract_catalog_cards(page,source,url):
    """Conservative fallback for storefronts that show products only as list/table rows.

    Accept only rows with an actual title, explicit USD and a numeric stock.
    A stable synthetic ID is derived from the product name and category URL when no ID exists.
    """
    import hashlib
    cards=page.locator('tr,article,[data-product-id],.product-card,.product-item,.goods-item,.goods-card').evaluate_all('''els => els.map(el => ({
      text: (el.innerText || '').trim(),
      title: (el.querySelector('h3,h4,h2,[class*=name],[class*=title]')?.innerText || '').trim(),
      id: el.getAttribute('data-product-id') || el.getAttribute('data-goods-id') || el.getAttribute('data-id') || '',
      href: el.querySelector('a[href]')?.getAttribute('href') || '',
      cells: [...el.querySelectorAll('td')].map(x => (x.innerText||'').trim())
    })).filter(x=>x.text.length>4)''')
    result=[];seen=set()
    for c in cards:
        text=c['text'];name=c['title']
        if not name and len(c['cells'])>=3:name=c['cells'][0]
        name=re.sub(r'\s+',' ',name).strip()
        if not 3<=len(name)<=180:continue
        stock=re.search(r'(?:库存|现货|存货|Stock|Inventory)\s*[:：]?\s*(\d+)',text,re.I)
        price=re.search(r'(?:USD\s*\$?\s*|\$\s*)(\d+(?:\.\d{1,4})?)',text)
        if len(c['cells'])>=3:
            stock=stock or re.search(r'^(\d+)$',c['cells'][1].strip())
            price=price or re.search(r'^\$\s*(\d+(?:\.\d{1,4})?)$',c['cells'][2].strip())
        if not stock or not price:continue
        item_url=canonical_url(source,c['href'],url) if c['href'] else None
        stable=c['id'] or ('listing-'+hashlib.sha256((urlparse(url).query+'|'+name).encode()).hexdigest()[:18])
        if (stable,name) in seen:continue
        seen.add((stable,name))
        result.append({'source':source,'external_id':stable,'name':name,'price':price.group(1),
            'stock':int(stock.group(1)),'url':item_url if item_url and is_detail(source,item_url) else url})
    return result
