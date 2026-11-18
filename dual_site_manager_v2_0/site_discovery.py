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
import json
from browser_collect import ALLOWED, dismiss_site_popup

ROOTS = {'FB1314': 'https://fb1314.com/', 'CEOACC': 'https://ceoacc.com/'}
SKIP = re.compile(r'/(?:cart|checkout|pay|payment|order|login|register|logout|user|account|support|contact|privacy|terms|api|admin)(?:/|$)', re.I)
ASSET = re.compile(r'\.(?:css|js|png|jpe?g|webp|gif|svg|ico|pdf|zip|rar|exe|mp4)(?:$|\?)', re.I)
DETAIL = re.compile(r'/(?:goods|product|products|item|detail)/[^/]+', re.I)
CATEGORY = re.compile(r'(?:category|categories|catalog|shop|list|goods-type|type|/sort/|/class/|/category/|[?&](?:category_id|category|cat|sort|type)=)',re.I)
MONEY = re.compile(r'(?:USD\s*\$?\s*|\$\s*)(\d+(?:\.\d{1,4})?)',re.I)
STOCK = re.compile(r'(?:库存|现货|存货|剩余|stock|inventory)\s*[:：]?\s*(\d[\d,]*)',re.I)
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
 const stockR=/(?:库存|现货|存货|剩余|stock|inventory)\s*[:：]?\s*\d/i;
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
            if not stock:stock=re.search(r'^\s*(?:剩余|库存)?\s*[:：]?\s*(\d[\d,]*)\s*$',cells[1])
            if not price:price=MONEY.search(cells[2])
        if not price or not stock:
            # A heading or navigation label is not necessarily a product card.
            # Count it as incomplete only when the candidate has product identity
            # (link/data ID) or explicit inventory/price evidence; this avoids
            # rejecting every scan because unrelated page headings were selected.
            product_evidence = bool(c.get('href') or c.get('id') or MONEY.search(text) or STOCK.search(text)
                                    or any(MONEY.search(str(cell)) or STOCK.search(str(cell)) for cell in cells))
            if product_evidence:
                incomplete+=1
            continue
        link=canonical_url(source,c.get('href') or '',page_url) if c.get('href') else None
        item_id=stable_id(source,name,link,c.get('id'))
        try:quantity=int(stock.group(1).replace(',',''))
        except ValueError:incomplete+=1;continue
        key=item_id
        valid[key]={'source':source,'external_id':item_id,'name':name,
                    'price':price.group(1),'stock':quantity,'url':link or page_url}
    return list(valid.values()),incomplete


# Fast, conservative progressive loading: only the page or the most likely product
# scroller is moved, rather than every scrollable UI element (menus, sidebars, etc.).
SCROLL_STATE_JS = r'''() => {
  const root=document.scrollingElement || document.documentElement;
  const selectors=['[class*="product-list"]','[class*="goods-list"]','[class*="productList"]',
      '[class*="goodsList"]','main [class*="scroll"]','main [class*="list"]'];
  const candidates=[];
  for(const selector of selectors){
    for(const e of document.querySelectorAll(selector)){
      if(e.scrollHeight>e.clientHeight+160 && e.clientHeight>240 && e.getBoundingClientRect().width>300){
        candidates.push(e);
      }
    }
  }
  const el=candidates.sort((a,b)=>b.clientHeight-a.clientHeight)[0] || root;
  const before=el.scrollTop;
  el.scrollTop=Math.min(el.scrollHeight,el.scrollTop+Math.max(500,Math.floor(el.clientHeight*0.88)));
  const after=el.scrollTop;
  const bottom=after+el.clientHeight>=el.scrollHeight-16;
  const text=(document.body?.innerText||'').slice(-4500);
  const endHint=/(已经到底|没有更多商品|没有更多了|已加载全部|no more (?:items|products)|end of (?:the )?list)/i.test(text);
  return {moved:after>before+2,bottom, endHint, height:el.scrollHeight, top:after,
          target:el===root?'document':'product-container'};
}'''


def should_finish_scroll(no_new_rounds, at_bottom, end_hint, any_valid, rounds):
    """Deterministic stop policy; a lack of products is not a success."""
    if end_hint and no_new_rounds >= 2:
        return True, bool(any_valid)
    if at_bottom and no_new_rounds >= 3:
        return True, bool(any_valid)
    if not any_valid and rounds >= 5 and no_new_rounds >= 4:
        return True, False
    return False, False



def wait_for_catalogue_signal(page, timeout_ms=18000, source=None):
    """Wait for a real, stable catalogue render instead of racing category navigation.

    CEOACC receives a longer hydration window and requires the visible listing
    signature to remain stable across several samples. We do not click through
    individual product details.
    """
    timeout_ms = max(timeout_ms, 18000 if source == 'CEOACC' else 9000)
    signal = r"""() => {
      const text=(document.body?.innerText||'');
      const money=/(?:USD\s*\$?\s*|\$\s*)\d+(?:\.\d{1,4})?/i.test(text);
      const stock=/(?:库存|现货|存货|剩余|stock|inventory)\s*[:：]?\s*\d/i.test(text);
      const rows=document.querySelectorAll('tbody tr,[data-product-id],[data-goods-id],.product-card,.goods-item,.product-item').length;
      const end=/(已经到底|没有更多商品|没有更多了|已加载全部|no more (?:items|products)|end of (?:the )?list)/i.test(text);
      return {ready:(money && stock && rows>0) || end, rows, tail:text.slice(-1200)};
    }"""
    try:
        page.wait_for_function(f"""() => {{
          const x=({signal})();
          if (!x.ready) {{ window.__bbStable = 0; window.__bbSig = ''; return false; }}
          const sig=String(x.rows)+'|'+x.tail.slice(-350);
          if (window.__bbSig === sig) window.__bbStable=(window.__bbStable||0)+1;
          else {{ window.__bbSig=sig; window.__bbStable=0; }}
          return window.__bbStable >= 2;
        }}""", timeout=timeout_ms)
        return True
    except Exception as exc:
        # A Playwright timeout is genuinely different from a JavaScript/browser
        # execution failure. Keep the latter visible in failed-pages diagnostics.
        if exc.__class__.__name__ == 'TimeoutError':
            return False
        raise RuntimeError(f'商品列表就绪检测执行异常: {type(exc).__name__}: {exc}') from exc


def write_scan_diagnostic(diag_dir, source, stats, errors, visited_pages, product_count):
    """Persist compact diagnostic JSON; fall back to Documents if configured path is unavailable."""
    from datetime import datetime
    import os, tempfile
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    report={
        'source':source, 'created_at':datetime.now().astimezone().isoformat(timespec='seconds'),
        'stats':stats, 'product_count':int(product_count),
        'visited_pages':visited_pages, 'errors':list(errors[:100]),
        'note':'Coverage describes visible public catalogue pages only; it is not a guarantee of private or login-restricted inventory.'
    }
    local_app = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    candidates=[Path(diag_dir),
                Path.home()/'Documents'/'DualSiteInventory'/'Diagnostics'/source.lower(),
                local_app/'DualSiteInventory'/'Diagnostics'/source.lower(),
                Path(tempfile.gettempdir())/'DualSiteInventory'/'Diagnostics'/source.lower()]
    last_error=None
    for folder in candidates:
        try:
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/f'scan_report_{stamp}.json'
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            # Also append a concise machine-readable index for easy discovery.
            with (folder/'scan_history.jsonl').open('a',encoding='utf-8') as fp:
                fp.write(json.dumps({'created_at':report['created_at'],'report':str(path),
                                     'product_count':int(product_count),'failed':stats.get('failed',0),
                                     'incomplete_cards':stats.get('incomplete_cards',0)},ensure_ascii=False)+'\n')
            return str(path)
        except OSError as exc:
            last_error=exc
    raise OSError(f'无法保存采集诊断报告；尝试目录：{diag_dir}；备用目录：{candidates[-1]}；原因：{last_error}')


def scroll_catalogue(page, source, url, max_scrolls=90, delay_ms=650, progress=None, stop=None,
                     time_budget_s=120):
    """Read while scrolling and stop on stable growth or a safety limit.

    Returns explicit completeness=false when no products are recognized or when
    time/round limits stop the scan. Does not infer completeness from time alone.
    """
    seen={};incomplete=0;rounds=0;completed=False;reason='max_scrolls'
    no_new_rounds=0;start=time.monotonic()
    for rounds in range(1,max_scrolls+1):
        if stop and stop.is_set():
            reason='cancelled';break
        if time.monotonic()-start >= time_budget_s:
            reason='time_budget';break
        records,missing=parse_listing_cards(source,get_listing_candidates(page),url)
        incomplete=max(incomplete,missing)
        before_count=len(seen)
        for record in records:seen[record['external_id']]=record
        growth=len(seen)-before_count
        no_new_rounds=0 if growth else no_new_rounds+1
        state=page.evaluate(SCROLL_STATE_JS)
        should_end,valid_end=should_finish_scroll(no_new_rounds,state['bottom'],state['endHint'],len(seen)>0,rounds)
        if progress and (rounds==1 or growth or rounds%3==0 or should_end):
            progress({'stage':'正在读取商品列表' if not should_end else '列表检查结束',
                      'scroll_round':rounds,'listed':len(seen),'new_in_round':growth,
                      'incomplete_cards':incomplete,'scroll_target':state['target'],
                      'idle_rounds':no_new_rounds})
        if should_end:
            completed=valid_end
            reason='stable_end' if valid_end else 'no_recognized_products'
            break
        # Allow JavaScript-loaded rows to arrive, without a fixed multi-second pause.
        # A brief longer settle happens at the end or while the list is quiet.
        settle_ms=max(250,min(1300,int(delay_ms)+(250 if state['bottom'] or no_new_rounds else 0)))
        page.wait_for_timeout(settle_ms)
    return list(seen.values()), {'scroll_rounds':rounds,'incomplete_cards':incomplete,
                                 'scroll_completed':completed,'scroll_capped':not completed,
                                 'stop_reason':reason,'elapsed_s':round(time.monotonic()-start,2)}


def pagination_links(page, source, base):
    """Return same-site catalogue pagination URLs without following product links.

    Only explicit pagination controls are accepted: rel=next, aria-labelled
    next controls, or anchors inside known pagination containers.
    """
    js = """els => els.map(a => ({
      href:a.getAttribute('href'), text:(a.innerText||'').trim(),
      rel:(a.getAttribute('rel')||'').toLowerCase(),
      aria:(a.getAttribute('aria-label')||'').toLowerCase(),
      cls:(a.className||'').toString().toLowerCase(),
      parent:(a.parentElement?.className||'').toString().toLowerCase()
    }))"""
    rows = page.locator('a[href]').evaluate_all(js)
    result=[]; seen=set()
    for row in rows:
        href=row.get('href') or ''
        marker=' '.join((row.get('rel',''),row.get('aria',''),row.get('cls',''),row.get('parent','')))
        text=row.get('text','').strip().lower()
        explicit_next = 'next' in marker or text in {'下一页','下页','›','»','>','next'}
        pagination_context = any(token in marker for token in ('pagination','pager','page-item','pages'))
        numbered = bool(re.fullmatch(r'\d{1,5}', text)) and pagination_context
        if not (explicit_next or numbered):
            continue
        target=canonical_url(source, href, base) if href else None
        if not target or target in seen or is_detail(source,target):
            continue
        result.append(target);seen.add(target)
    return result


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
              max_scrolls=90,scroll_delay_ms=650, selected_categories=None):
    """List-first scan. Pages are homepage/category only, never product detail.

    No completeness guarantee for unlisted/private products. Emits coverage
    diagnostics and snapshots rather than fabricating prices/stocks.
    """
    from playwright.sync_api import sync_playwright
    root=ROOTS[source]
    profile=Path(profiles_dir)/source.lower();profile.mkdir(parents=True,exist_ok=True)
    diag=Path(diagnosis_dir)/source.lower();diag.mkdir(parents=True,exist_ok=True)
    # When selected, only explicit category URLs are visited; homepage cannot
    # accidentally introduce excluded catalogue products into the database.
    selected_categories=set(selected_categories) if selected_categories is not None else None
    if selected_categories is not None:
        invalid=[u for u in selected_categories if canonical_url(source,u,root)!=u or is_detail(source,u)]
        if invalid:raise ValueError('类目 URL 不安全或不是本站分类链接')
        if not selected_categories:raise ValueError('尚未选择任何需要采集的类目')
    seeds=sorted(selected_categories) if selected_categories is not None else [root]
    queue=deque(seeds);queued=set(seeds);seen_pages=set();products={};errors=[]
    stats={'source':source,'visited':0,'listed':0,'incomplete_cards':0,'scroll_rounds':0,
           'failed':0,'truncated':False,'coverage':'unverified','detail_visits':0,
           'category_pages_found':0,'pagination_pages_found':0}
    visited_pages=[]
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=not headed,
                    viewport={'width':1280,'height':900},locale='zh-CN',accept_downloads=False)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            while queue and stats['visited']<max_pages:
                if stop and stop.is_set():break
                url=queue.popleft();queued.discard(url)
                if url in seen_pages:continue
                if progress:progress({**stats,'stage':'正在打开分类或商品列表','current_url':url,'queued':len(queue)})
                seen_pages.add(url)
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    dismiss_site_popup(page,source)
                    # Adaptive wait for client-rendered lists; do not rely on networkidle
                    # because storefronts may keep analytics/polling requests open.
                    ready=wait_for_catalogue_signal(page, timeout_ms=(22000 if source=='CEOACC' else 12000), source=source)
                    if not ready:
                        raise RuntimeError('等待商品列表稳定超时；页面未出现稳定的商品名称/价格/库存结构')
                    if urlparse(page.url).hostname not in ALLOWED[source]:raise RuntimeError('跳转到非本站页面')
                    title=page.title()
                    if re.search(r'captcha|cloudflare|verify you are human|安全验证',title,re.I):
                        raise RuntimeError('遇到安全验证，请人工处理')
                    # Gather catalogue category links before scrolling/DOM re-render.
                    links=category_links(page,source,page.url)
                    pages=pagination_links(page,source,page.url)
                    stats['category_pages_found'] += len(links)
                    stats['pagination_pages_found'] += len(pages)
                    visited_pages.append({'url':page.url,'title':title,'category_links':len(links),
                                          'pagination_links':len(pages)})
                    def scroll_report(event):
                        if progress:
                            progress({**stats, **event, 'visited':stats['visited'],
                                      'listed':len(products)+event.get('listed',0),
                                      'incomplete_cards':stats['incomplete_cards']+event.get('incomplete_cards',0),
                                      'current_url':url,'queued':len(queue)})
                    effective_delay = max(scroll_delay_ms, 1250) if source == 'CEOACC' else scroll_delay_ms
                    items,result=scroll_catalogue(page,source,page.url,max_scrolls,effective_delay,scroll_report,stop,
                                                  time_budget_s=(240 if source=='CEOACC' else 150))
                    stats['visited']+=1
                    stats['scroll_rounds']+=result['scroll_rounds']
                    stats['incomplete_cards']+=result['incomplete_cards']
                    if result['scroll_capped']:
                        stats['truncated']=True
                        errors.append(f'{url}: 滚动未达到稳定结束条件，商品可能未加载完整')
                    for item in items:
                        key=(item['external_id'],item.get('variant',''))
                        if key not in products:
                            item['category_keys']=[url]
                            products[key]=item
                        elif url not in products[key]['category_keys']:
                            products[key]['category_keys'].append(url)
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
                        # Follow explicit pagination in both full-site and selected-category scans.
                        # Selected mode still never discovers unrelated categories.
                        for link in pages:
                            if link not in queued and link not in seen_pages:
                                queue.append(link);queued.add(link)
                        if selected_categories is None:
                            for link in links:
                                if link not in queued and link not in seen_pages:
                                    queue.append(link);queued.add(link)
                    if progress:progress({**stats,'stage':'本页读取完成','current_url':url,'queued':len(queue),'pagination_found':len(pages)})
                except Exception as exc:
                    stats['failed']+=1;errors.append(f'{url}: {exc}')
                    try:
                        visited_pages.append({'url':url,'title':page.title(),'error':str(exc),
                                              'selector_count':page.locator(CARD_SELECTORS).count(),
                                              'fallback_count':len(page.evaluate(PROXIMITY_JS))})
                    except Exception:
                        visited_pages.append({'url':url,'error':str(exc)})
                    if stats['failed']<=12:
                        try:page.screenshot(path=str(diag/f'scan_{int(time.time()*1000)}.png'),timeout=5000)
                        except Exception:pass
                time.sleep(0.25)
        finally:context.close()
    # Any product-like card missing required name/USD/stock data makes the
    # run unsuitable as a complete inventory snapshot. Keep the visible rows
    # for diagnosis, but fail closed at the task layer.
    stats['truncated']= (stats['truncated'] or bool(queue) or bool(stop and stop.is_set())
                         or stats['failed']>0 or stats['incomplete_cards']>0)
    stats['coverage']='incomplete' if stats['truncated'] else 'visible_catalogues_only'
    if stats['listed']==0:
        stats['truncated']=True
    stats['diagnostic_report']=write_scan_diagnostic(diag,source,stats,errors,visited_pages,len(products))
    if progress:progress({**stats,'stage':'扫描结束','current_url':'','queued':len(queue)})
    return list(products.values()),errors,stats

# Legacy compatibility name used by single-link diagnostics.
def extract_catalog_cards(page,source,url):
    return parse_listing_cards(source,get_listing_candidates(page),url)[0]


def discover_site_categories(source, profiles_dir, diagnosis_dir, headed=True):
    """Discover public category anchors only, without scanning product detail pages.
    Results remain unverified until the user enables them and scans their rows.
    """
    from playwright.sync_api import sync_playwright
    root=ROOTS[source]
    profile=Path(profiles_dir)/source.lower();profile.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        context=p.chromium.launch_persistent_context(user_data_dir=str(profile),headless=not headed,
                    viewport={'width':1280,'height':900},locale='zh-CN')
        try:
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(root,wait_until='domcontentloaded',timeout=35000)
            dismiss_site_popup(page,source)
            page.wait_for_timeout(1200)
            links=page.locator('a[href]').evaluate_all("els=>els.map(e=>({href:e.getAttribute('href'),text:(e.innerText||'').trim()}))")
            categories={}
            for row in links:
                href=row.get('href')
                url=canonical_url(source,href,page.url) if href else None
                if not url or url==root or is_detail(source,url):continue
                title=re.sub(r'\s+',' ',row.get('text') or '').strip()[:120]
                if not title:continue
                if CATEGORY.search(url):categories[url]={'key':url,'title':title}
            return list(categories.values())
        finally:context.close()
