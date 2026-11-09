"""List-first catalogue discovery for FB1314 and CEOACC.

Only public catalogue pages, no checkout, account or CAPTCHA bypass. Product
cards are read in batches while the page is scrolled; product details are NOT
visited. Missing numeric USD price or inventory is reported, never invented.
"""
from collections import deque
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
import re
import time
from browser_collect import ALLOWED, dismiss_site_popup

ROOTS = {'FB1314': 'https://fb1314.com/', 'CEOACC': 'https://ceoacc.com/'}
SKIP = re.compile(r'/(?:cart|checkout|pay|payment|order|login|register|logout|user|account|support|contact|privacy|terms|api|admin)(?:/|$)', re.I)
ASSET = re.compile(r'\.(?:css|js|png|jpe?g|webp|gif|svg|ico|pdf|zip|rar|exe|mp4)(?:$|\?)', re.I)
DETAIL = re.compile(r'/(?:goods|product|products|item|detail)/[^/]+', re.I)
CATEGORY = re.compile(r'(?:category|categories|catalog|shop|list|goods-type|type|/sort/|/class/|/category/|[?&](?:category_id|category|cat|sort|type)=)',re.I)
MONEY = re.compile(r'(?:USD\s*\$?\s*|\$\s*)(\d+(?:\.\d{1,4})?)',re.I)
STOCK = re.compile(r'(?:库存|现货|存货|stock|inventory)\s*[:：]?\s*(\d[\d,]*)',re.I)
# Site pages render asynchronously. Discover cards by explicit product selectors first,
# then use a DOM-proximity pass around displayed prices/stock rather than relying on
# a single brittle CSS class. This never guesses missing currency or inventory.
CARD_JS = r'''els => els.map(el => {
 const txt = (el.innerText || '').trim();
 const titleElement = el.querySelector('[data-product-name],[data-goods-name],.goods-name,.product-name,[class*="goodsName"],[class*="productName"],h2,h3,h4,[class*="title"],[class*="name"]');
 const name = (titleElement?.innerText || '').trim();
 const href = el.querySelector('a[href*="goods/"],a[href*="product"],a[href*="detail"],a[href]')?.getAttribute('href') || '';
 const cells = [...el.querySelectorAll('td')].map(x => (x.innerText||'').trim());
 return {text:txt, name, href, cells,
   id: el.getAttribute('data-product-id') || el.getAttribute('data-goods-id') || el.getAttribute('data-id') || ''};
}).filter(x => x.text.length>=5 && x.text.length<=4000)'''
CARD_SELECTORS = 'tr[data-id],tbody tr,article,[data-product-id],[data-goods-id],.product-card,.product-item,.goods-item,.goods-card,[class*="goodsItem"],[class*="productCard"],[class*="product-item"],[class*="goods-card"],[class*="goods-item"],li[class*="product"],li[class*="goods"]'

# Detect repeated visible product-like containers by walking up from exact price
# nodes. Sitewide $0.00 balance and modal prices must never be counted as products.
PROXIMITY_JS = r'''() => {
 const result=[], uniq=new Set();
 const priceR=/((?:USD\s*\$?\s*|\$\s*)\d+(?:\.\d{1,4})?)/i;
 const stockR=/(?:库存|现货|存货|stock|inventory)\s*[:：]?\s*\d/i;
 const excluded=el=>Boolean(el.closest('header,footer,nav,[role="dialog"],[aria-modal="true"],aside'));
 for (const node of document.querySelectorAll('span,b,strong,p,td,small,div')) {
   if(result.length >= 15000)break;
   if(node.children.length>4 || excluded(node))continue;
   const val=(node.innerText||'').trim();
   if(val.length>120 || !priceR.test(val))continue;
   let card=node;
   for(let depth=0;depth<6 && card;depth++,card=card.parentElement){
      if(excluded(card))break;
      const txt=(card.innerText||'').trim();
      if(txt.length<12 || txt.length>1800 || !stockR.test(txt))continue;
      const title=card.querySelector('[data-product-name],[data-goods-name],.goods-name,.product-name,h2,h3,h4,[class*="goodsName"],[class*="productName"],[class*="title"],[class*="name"]');
      let name=(title?.innerText||'').trim();
      // Prefer the first data row cell if the product is presented as a table.
      const cells=[...card.querySelectorAll('td')].map(c=>(c.innerText||'').trim());
      if(!name && cells.length>=3)name=cells[0];
      // In FB1314 cards the product title is often just ordinary text above a price.
      if(!name) {
        const lines=txt.split('\n').map(s=>s.trim()).filter(Boolean);
        name=lines.find(l=>l.length>=3 && l.length<=180 && !priceR.test(l) && !stockR.test(l) && !/^(立即购买|购买|推荐|操作|已售罄|Sold Out)$/i.test(l))||'';
      }
      const a=card.querySelector('a[href*="/goods/"],a[href*="/product"],a[href*="/detail"],a[href]');
      const href=a?.getAttribute('href')||'';
      const id=card.getAttribute('data-product-id')||card.getAttribute('data-goods-id')||card.getAttribute('data-id')||'';
      const key=[name,href,txt.slice(-160)].join('|');
      if(name && !uniq.has(key)){
        uniq.add(key);result.push({text:txt,name,href,cells,id});
      }
      break;
   }
 }
 return result;
}'''


def get_listing_candidates(page):
    cards=page.locator(CARD_SELECTORS).evaluate_all(CARD_JS)
    proximity=page.evaluate(PROXIMITY_JS)
    return cards+proximity


def canonical_url(source, href, base):
    target=urldefrag(urljoin(base,href))[0]
    p=urlparse(target)
    if p.scheme!='https' or p.hostname not in ALLOWED[source] or p.username or p.password:
        return None
    if SKIP.search(p.path) or ASSET.search(p.path):
        return None
    return target.rstrip('/') if p.path != '/' else target


def is_detail(source,url):
    return bool(DETAIL.search(urlparse(url).path))


def stable_id(source, name, href=None, raw_id=None):
    if raw_id and str(raw_id).strip():return str(raw_id).strip()
    if href:
        match=re.search(r'/goods/(\d+)\.html',urlparse(href).path,re.I)
        if match:return match.group(1)
        match=re.search(r'/(?:product|products|goods|item|detail)/([\w-]+)',urlparse(href).path,re.I)
        if match:return match.group(1)
    return 'listing-'+sha256((source+'|'+re.sub(r'\s+',' ',name.strip()).casefold()).encode()).hexdigest()[:20]


def parse_listing_cards(source, data, page_url):
    """Parse candidate listing rows; return (records, incomplete_count).

    Item links are metadata only: no per-product navigation. When no durable
    URL is available, use the source catalogue URL and stable title fingerprint.
    """
    valid={};incomplete=0
    for c in data:
        text=re.sub(r'[ \t]+',' ',c.get('text') or '').strip()
        cells=c.get('cells') or []
        name=re.sub(r'\s+',' ',c.get('name') or '').strip()
        if not name and len(cells)>=3:
            name=re.sub(r'\s+',' ',cells[0]).strip()
        # Product name must be explicit, not inferred from a random page region.
        if len(name)<3 or len(name)>250:continue
        price=MONEY.search(text)
        stock=STOCK.search(text)
        if len(cells)>=3:
            if not stock:stock=re.search(r'^\s*(\d[\d,]*)\s*$',cells[1])
            if not price:price=MONEY.search(cells[2])
        if not price or not stock:
            incomplete+=1;continue
        link=canonical_url(source,c.get('href') or '',page_url) if c.get('href') else None
        item_id=stable_id(source,name,link,c.get('id'))
        try:quantity=int(stock.group(1).replace(',',''))
        except ValueError:incomplete+=1;continue
        key=item_id
        valid[key]={'source':source,'external_id':item_id,'name':name,
                    'price':price.group(1),'stock':quantity,'url':link or page_url}
    return list(valid.values()),incomplete


def scroll_catalogue(page, source, url, max_scrolls=180, delay_ms=1800, progress=None, stop=None):
    """Incrementally scroll main document and scrollable product containers.

    Finish only after stable DOM counts *and* stable scroll position; do not
    falsely report complete if a safety cap, timeout or challenge stops scan.
    """
    seen={};incomplete=0;stable=0;last_marker=None;rounds=0;terminated=False
    for rounds in range(1,max_scrolls+1):
        if stop and stop.is_set():break
        candidates=get_listing_candidates(page)
        records,missing=parse_listing_cards(source,candidates,url)
        incomplete=max(incomplete,missing)
        for record in records:seen[record['external_id']]=record
        # These scrollable containers cover sites which render product lists in panels.
        marker=page.evaluate('''() => {
          const nodes=[document.scrollingElement,...document.querySelectorAll('main,section,[class*=scroll],[class*=list]')];
          let movable=0;
          for (const e of nodes) {
            if(!e)continue;
            if(e===document.scrollingElement || (e.scrollHeight>e.clientHeight+100 && e.clientHeight>200)){
              const from=e.scrollTop; e.scrollTop=Math.min(e.scrollHeight,e.scrollTop+Math.max(500,Math.floor(e.clientHeight*.8)));
              if(e.scrollTop>from+2)movable++;
            }
          }
          return {height:document.scrollingElement.scrollHeight,top:document.scrollingElement.scrollTop,movable};
        }''')
        page.wait_for_timeout(delay_ms)
        updated=page.locator(CARD_SELECTORS).count()
        fingerprint=(len(seen),updated,marker['height'],marker['top'])
        stable=stable+1 if fingerprint==last_marker and marker['movable']==0 else 0
        last_marker=fingerprint
        if progress and rounds%5==0:progress({'scroll_round':rounds,'listed':len(seen),'incomplete_cards':incomplete})
        if stable>=3:
            terminated=True;break
    return list(seen.values()), {'scroll_rounds':rounds,'incomplete_cards':incomplete,
                                 'scroll_completed':terminated,'scroll_capped':not terminated}


def category_links(page,source,base):
    """Only publicly linked catalogue/category pages; explicitly exclude details."""
    data=page.locator('a[href]').evaluate_all('''els => els.map(e=>({href:e.getAttribute('href'),text:(e.innerText||'').trim()}))''')
    result=[];seen=set()
    for row in data:
        href=row.get('href'); dest=canonical_url(source,href,base) if href else None
        if not dest or dest in seen or dest==ROOTS[source] or is_detail(source,dest):continue
        label=row.get('text') or ''
        if CATEGORY.search(dest) or ('/' not in urlparse(dest).path.strip('/') and 1<=len(label)<=36 and '分类' in label):
            result.append(dest);seen.add(dest)
    return result


def scan_site(source,profiles_dir,diagnosis_dir,max_pages=120,headed=True,stop=None,progress=None,
              max_scrolls=180,scroll_delay_ms=1800):
    """List-first scan. Pages are homepage/category only, never product detail.

    No completeness guarantee for unlisted/private products. Emits coverage
    diagnostics and snapshots rather than fabricating prices/stocks.
    """
    from playwright.sync_api import sync_playwright
    root=ROOTS[source]
    profile=Path(profiles_dir)/source.lower();profile.mkdir(parents=True,exist_ok=True)
    diag=Path(diagnosis_dir)/source.lower();diag.mkdir(parents=True,exist_ok=True)
    queue=deque([root]);queued={root};seen_pages=set();products={};errors=[]
    stats={'source':source,'visited':0,'listed':0,'incomplete_cards':0,'scroll_rounds':0,
           'failed':0,'truncated':False,'coverage':'unverified','detail_visits':0}
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=not headed,
                    viewport={'width':1280,'height':900},locale='zh-CN',accept_downloads=False)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            while queue and stats['visited']<max_pages:
                if stop and stop.is_set():break
                url=queue.popleft();queued.discard(url)
                if url in seen_pages:continue
                seen_pages.add(url)
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    dismiss_site_popup(page,source)
                    # Public catalogue is client-rendered; DOMContentLoaded alone is too early.
                    page.wait_for_timeout(2200)
                    if urlparse(page.url).hostname not in ALLOWED[source]:raise RuntimeError('跳转到非本站页面')
                    title=page.title()
                    if re.search(r'captcha|cloudflare|verify you are human|安全验证',title,re.I):
                        raise RuntimeError('遇到安全验证，请人工处理')
                    # Gather catalogue category links before scrolling/DOM re-render.
                    links=category_links(page,source,page.url)
                    items,result=scroll_catalogue(page,source,page.url,max_scrolls,scroll_delay_ms,progress,stop)
                    stats['visited']+=1
                    stats['scroll_rounds']+=result['scroll_rounds']
                    stats['incomplete_cards']+=result['incomplete_cards']
                    if result['scroll_capped']:
                        stats['truncated']=True
                        errors.append(f'{url}: 滚动未达到稳定结束条件，商品可能未加载完整')
                    for item in items:products[item['external_id']]=item
                    stats['listed']=len(products)
                    if not items:
                        # Preserve a diagnostic screenshot and a small structural report.
                        # Never export full page HTML, cookies, or tokens.
                        try:
                            page.screenshot(path=str(diag/f'empty_{stats["visited"]}_{int(time.time())}.png'), timeout=6000)
                            report={'url':page.url,'title':page.title(),
                                    'selector_count':page.locator(CARD_SELECTORS).count(),
                                    'fallback_count':len(page.evaluate(PROXIMITY_JS)),
                                    'scroll_rounds':result['scroll_rounds'],
                                    'incomplete_cards':result['incomplete_cards']}
                            import json
                            (diag/f'empty_{stats["visited"]}_{int(time.time())}.json').write_text(
                                json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                        except Exception:pass
                        errors.append(f'{url}: 页面已加载但未找到可确认的商品名称、USD价格和数字库存；已保存诊断')
                    if stats['visited']<max_pages:
                        for link in links:
                            if link not in queued and link not in seen_pages:
                                queue.append(link);queued.add(link)
                    if progress:progress(dict(stats))
                except Exception as exc:
                    stats['failed']+=1;errors.append(f'{url}: {exc}')
                    if stats['failed']<=12:
                        try:page.screenshot(path=str(diag/f'scan_{int(time.time()*1000)}.png'),timeout=5000)
                        except Exception:pass
                time.sleep(0.7)
        finally:context.close()
    stats['truncated']=stats['truncated'] or bool(queue) or bool(stop and stop.is_set()) or stats['failed']>0
    stats['coverage']='incomplete' if stats['truncated'] else 'visible_catalogues_only'
    if stats['listed']==0:
        stats['truncated']=True
    if progress:progress(dict(stats))
    return list(products.values()),errors,stats

# Legacy compatibility name used by single-link diagnostics.
def extract_catalog_cards(page,source,url):
    return parse_listing_cards(source,get_listing_candidates(page),url)[0]
