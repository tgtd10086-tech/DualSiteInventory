"""Offline-first inventory management core. No account credentials stored in SQLite."""
import csv
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

SOURCES = ('FB1314', 'CEOACC')

def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def usd(value):
    try:
        result = Decimal(str(value).replace('$','').replace(',','').strip())
        if not result.is_finite() or result < 0: raise ValueError('invalid price')
        return str(result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise ValueError('价格必须是非负 USD 数值')

def _stock(value):
    if value in ('', None, 'unknown'):
        return None
    v = int(value)
    if v < 0: raise ValueError('库存不能小于零')
    return v

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self._init()

    def _init(self):
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
          variant TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
          raw_usd TEXT NOT NULL, stock INTEGER, status TEXT NOT NULL DEFAULT 'review',
          first_seen TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(source, external_id, variant));
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
          captured_at TEXT NOT NULL, raw_usd TEXT NOT NULL, stock INTEGER,
          stock_delta INTEGER, price_delta TEXT, note TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS project_products (
          project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          custom_usd TEXT, sort_order INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(project_id, product_id));
        CREATE TABLE IF NOT EXISTS site_categories (
          id INTEGER PRIMARY KEY, source TEXT NOT NULL,
          category_key TEXT NOT NULL, title TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'review' CHECK(state IN ('review','enabled','paused','excluded')),
          detected_at TEXT NOT NULL, UNIQUE(source,category_key));
        CREATE TABLE IF NOT EXISTS product_categories (
          product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          category_id INTEGER NOT NULL REFERENCES site_categories(id) ON DELETE CASCADE,
          PRIMARY KEY(product_id,category_id));
        CREATE TABLE IF NOT EXISTS scan_runs (
          id INTEGER PRIMARY KEY, source TEXT NOT NULL, started_at TEXT NOT NULL,
          completed_at TEXT, coverage TEXT NOT NULL, found INTEGER NOT NULL DEFAULT 0,
          written INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
          detail TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS publish_log (
          id INTEGER PRIMARY KEY, project_id INTEGER, target TEXT, created_at TEXT,
          status TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS automation_jobs (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT '', project_id INTEGER,
          interval_minutes INTEGER NOT NULL, target TEXT NOT NULL DEFAULT '',
          caption TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
          next_run REAL NOT NULL DEFAULT 0, last_run TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_automation_due ON automation_jobs(enabled,next_run);
        CREATE INDEX IF NOT EXISTS idx_product_source ON products(source,status);
        CREATE INDEX IF NOT EXISTS idx_snapshots_product ON snapshots(product_id,captured_at);
        ''')
        # Safe, additive migrations for existing v0.1-v0.5 user databases.
        for table, columns in {
            'products': [('display_name','TEXT'),('display_usd','TEXT')],
            'project_products': [('custom_name','TEXT')],
            'projects': [('sales_periods',"TEXT NOT NULL DEFAULT '24h'")],
            'automation_jobs': [('daily_times',"TEXT NOT NULL DEFAULT ''")]
        }.items():
            existing={r['name'] for r in self.conn.execute(f'PRAGMA table_info({table})')}
            for col, typ in columns:
                if col not in existing:
                    self.conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
        self.conn.commit()

    def upsert(self, source, external_id, name, price, stock, variant='', url='', review_new=True):
        if source not in SOURCES: raise ValueError('不支持的数据来源')
        external_id = str(external_id).strip()
        if not external_id: raise ValueError('商品 ID 不可为空')
        variant = str(variant or '')
        name = str(name).strip()
        if not name: raise ValueError('名称不可为空')
        price = usd(price)
        stock = _stock(stock)
        t = now()
        with self.conn:
            old = self.conn.execute('SELECT * FROM products WHERE source=? AND external_id=? AND variant=?',
                                    (source,external_id,variant)).fetchone()
            if old:
                delta = (stock - old['stock']) if stock is not None and old['stock'] is not None else None
                pd = str(Decimal(price)-Decimal(old['raw_usd']))
                self.conn.execute('UPDATE products SET name=?,url=?,raw_usd=?,stock=?,updated_at=? WHERE id=?',
                    (name,url,price,stock,t,old['id']))
                pid = old['id']
            else:
                delta = None; pd = None
                cur = self.conn.execute('INSERT INTO products (source,external_id,variant,name,url,raw_usd,stock,status,first_seen,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (source,external_id,variant,name,url,price,stock,'review' if review_new else 'active',t,t))
                pid = cur.lastrowid
            self.conn.execute('INSERT INTO snapshots(product_id,captured_at,raw_usd,stock,stock_delta,price_delta,note) VALUES(?,?,?,?,?,?,?)',
                (pid,t,price,stock,delta,pd,'initial' if old is None else 'update'))
        return pid,delta

    def products(self, source='', status='', search=''):
        where=[]; params=[]
        if source: where.append('source=?');params.append(source)
        if status: where.append('status=?');params.append(status)
        if search: where.append('(name LIKE ? OR external_id LIKE ? OR COALESCE(display_name,"") LIKE ?)');params.extend(['%'+search+'%']*3)
        q = 'SELECT * FROM products' + (' WHERE '+' AND '.join(where) if where else '')+' ORDER BY updated_at DESC,id DESC'
        return self.conn.execute(q,params).fetchall()

    def set_display(self, product_id, name=None, price=None):
        # Never mutate original name/raw_usd or source identifiers.
        display_name = str(name or '').strip() or None
        display_usd = usd(price) if str(price or '').strip() else None
        with self.conn:
            self.conn.execute('UPDATE products SET display_name=?,display_usd=? WHERE id=?',
                              (display_name,display_usd,int(product_id)))

    def set_status(self, ids, status):
        if status not in ('review','active','paused','excluded'): raise ValueError('状态错误')
        with self.conn:
            self.conn.executemany('UPDATE products SET status=? WHERE id=?',[(status,int(i)) for i in ids])

    def add_project(self,name):
        with self.conn:
            self.conn.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',(name.strip(),now()))

    def projects(self):
        return self.conn.execute('SELECT * FROM projects ORDER BY id').fetchall()

    def set_project_periods(self,project_id,periods):
        allowed={'24h','7d','30d'}
        periods=list(dict.fromkeys(periods))
        if any(p not in allowed for p in periods):raise ValueError('不支持的销量周期')
        with self.conn:self.conn.execute('UPDATE projects SET sales_periods=? WHERE id=?',
                                         (','.join(periods),int(project_id)))

    def get_project_periods(self,project_id):
        r=self.conn.execute('SELECT sales_periods FROM projects WHERE id=?',(int(project_id),)).fetchone()
        return tuple(x for x in (r['sales_periods'].split(',') if r else []) if x in ('24h','7d','30d'))

    def project_assign(self, project_id, product_ids):
        with self.conn:
            self.conn.executemany('INSERT OR IGNORE INTO project_products(project_id,product_id) VALUES (?,?)',[(project_id,int(p)) for p in product_ids])

    def project_products(self,project_id):
        return self.conn.execute('''SELECT p.*,pp.custom_usd,pp.custom_name,pp.sort_order,
              COALESCE(NULLIF(pp.custom_name,''),NULLIF(p.display_name,''),p.name) AS effective_name,
              COALESCE(pp.custom_usd,p.display_usd) AS effective_usd
              FROM products p JOIN project_products pp ON pp.product_id=p.id
              WHERE pp.project_id=? ORDER BY pp.sort_order,p.id''',(project_id,)).fetchall()

    def set_project_price(self,project_id,product_id,price):
        with self.conn:
            self.conn.execute('UPDATE project_products SET custom_usd=? WHERE project_id=? AND product_id=?',
                (usd(price) if str(price).strip() else None,project_id,product_id))

    def set_project_display(self,project_id,product_id,name=None,price=None):
        with self.conn:
            self.conn.execute('''UPDATE project_products SET custom_name=?,custom_usd=?
                WHERE project_id=? AND product_id=?''',
                (str(name or '').strip() or None,
                 usd(price) if str(price or '').strip() else None,
                 int(project_id),int(product_id)))

    def history(self,product_id):
        return self.conn.execute('SELECT * FROM snapshots WHERE product_id=? ORDER BY id DESC LIMIT 500',(product_id,)).fetchall()

    def stats(self):
        result={}
        for source in SOURCES:
            r=self.conn.execute('SELECT COUNT(*) n, SUM(CASE WHEN status="review" THEN 1 ELSE 0 END) review FROM products WHERE source=?',(source,)).fetchone()
            result[source]={'count':r['n'],'review':r['review'] or 0}
        return result

    @staticmethod
    def next_daily_run(times, reference=None):
        """Return local timestamp for next scheduled HH:MM; no recurring timer drift."""
        import time
        instant=datetime.fromtimestamp(reference or time.time()).astimezone()
        candidates=[]
        for v in times.split(','):
            part=v.strip()
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',part):raise ValueError('固定时间需为 HH:MM，多个时间用英文逗号隔开')
            hour,minute=map(int,part.split(':'))
            candidate=instant.replace(hour=hour,minute=minute,second=0,microsecond=0)
            if candidate<=instant:candidate+=timedelta(days=1)
            candidates.append(candidate.timestamp())
        if not candidates:raise ValueError('至少设置一个固定执行时间')
        return min(candidates)

    def add_job(self,name,kind,interval_minutes,source='',project_id=None,target='',caption='',daily_times=''):
        if kind not in ('categories','discover','refresh','capture','publish'): raise ValueError('未知任务类型')
        if int(interval_minutes)<5:raise ValueError('任务间隔必须至少 5 分钟')
        import time
        when=self.next_daily_run(daily_times) if daily_times.strip() else time.time()+int(interval_minutes)*60
        with self.conn:
            cur=self.conn.execute('INSERT INTO automation_jobs(name,kind,source,project_id,interval_minutes,target,caption,next_run,daily_times) VALUES(?,?,?,?,?,?,?,?,?)',
                (name,kind,source,project_id,int(interval_minutes),target,caption,when,daily_times.strip()))
        return cur.lastrowid

    def jobs(self):
        return self.conn.execute('SELECT * FROM automation_jobs ORDER BY id').fetchall()

    def mark_job(self,job_id,error=''):
        import time
        job=self.conn.execute('SELECT daily_times,interval_minutes FROM automation_jobs WHERE id=?',(job_id,)).fetchone()
        if not job:return
        next_run=self.next_daily_run(job['daily_times']) if job['daily_times'] else time.time()+job['interval_minutes']*60
        with self.conn:
            self.conn.execute('UPDATE automation_jobs SET last_run=?,last_error=?,next_run=? WHERE id=?',
                (now(),str(error)[:1000],next_run,job_id))

    def delete_job(self,job_id):
        with self.conn:self.conn.execute('DELETE FROM automation_jobs WHERE id=?',(job_id,))


    # Site category identities are website URLs/identifiers, never custom project names.
    def register_categories(self, source, categories):
        if source not in SOURCES: raise ValueError('未知网站')
        with self.conn:
            for cat in categories:
                key=str(cat['key']).strip(); title=str(cat['title']).strip()
                if not key or not title: continue
                self.conn.execute('''INSERT INTO site_categories(source,category_key,title,detected_at)
                    VALUES (?,?,?,?) ON CONFLICT(source,category_key)
                    DO UPDATE SET title=excluded.title''',(source,key,title,now()))

    def categories(self,source=''):
        return self.conn.execute('SELECT * FROM site_categories'+(' WHERE source=?' if source else '')+
                                 ' ORDER BY source,state,title',((source,) if source else ())).fetchall()

    def set_category_state(self, category_ids, state):
        if state not in ('review','enabled','paused','excluded'): raise ValueError('类目状态错误')
        with self.conn:
            self.conn.executemany('UPDATE site_categories SET state=? WHERE id=?',
                                  [(state,int(cid)) for cid in category_ids])

    def enabled_category_keys(self,source):
        return {r['category_key'] for r in self.categories(source) if r['state']=='enabled'}

    def ingest_category_scan(self,source,records,category_keys,complete,failures=0,detail=''):
        """Fail closed: never promote a truncated scan to product history.
        All rows must belong to selected categories; original+custom values remain separate.
        """
        keys=set(category_keys)
        if not complete:
            with self.conn:
                self.conn.execute('INSERT INTO scan_runs(source,started_at,completed_at,coverage,found,failures,detail) VALUES(?,?,?,?,?,?,?)',
                                  (source,now(),now(),'incomplete',len(records),int(failures),str(detail)[:2000]))
            return 0
        if not keys: raise ValueError('没有启用的网站类目')
        selected=self.enabled_category_keys(source)
        if not keys.issubset(selected): raise ValueError('采集范围包含未启用类目，拒绝写入')
        clean={}
        for item in records:
            belongs=set(item.get('category_keys') or ([item['category_key']] if item.get('category_key') else [])) & keys
            if not belongs:continue
            ext=str(item['external_id']).strip();variant=str(item.get('variant') or '')
            if not ext:raise ValueError('商品缺少稳定ID')
            clean[(ext,variant)]=(item,belongs)
        t=now()
        # The entire batch is committed atomically, and rolled back if any item is invalid.
        written=0
        with self.conn:
            for (ext,variant),(item,belongs) in clean.items():
                name=str(item['name']).strip()
                if not name:raise ValueError('商品名称为空')
                price=usd(item['price']);stock=_stock(item['stock'])
                old=self.conn.execute('SELECT * FROM products WHERE source=? AND external_id=? AND variant=?',
                                      (source,ext,variant)).fetchone()
                if old and old['status'] in ('paused','excluded'):
                    continue
                if old:
                    pid=old['id']
                    delta=stock-old['stock'] if stock is not None and old['stock'] is not None else None
                    price_delta=str(Decimal(price)-Decimal(old['raw_usd']))
                    self.conn.execute('UPDATE products SET name=?,url=?,raw_usd=?,stock=?,updated_at=? WHERE id=?',
                                      (name,item.get('url',''),price,stock,t,pid))
                else:
                    delta=None;price_delta=None
                    pid=self.conn.execute('''INSERT INTO products(source,external_id,variant,name,url,raw_usd,stock,status,first_seen,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?)''',(source,ext,variant,name,item.get('url',''),price,stock,'review',t,t)).lastrowid
                self.conn.execute('''INSERT INTO snapshots(product_id,captured_at,raw_usd,stock,stock_delta,price_delta,note)
                    VALUES(?,?,?,?,?,?,?)''',(pid,t,price,stock,delta,price_delta,'category_scan'))
                written+=1
                for catkey in belongs:
                    cat=self.conn.execute('SELECT id FROM site_categories WHERE source=? AND category_key=? AND state="enabled"',
                                          (source,catkey)).fetchone()
                    if cat:self.conn.execute('INSERT OR IGNORE INTO product_categories(product_id,category_id) VALUES(?,?)',(pid,cat['id']))
            self.conn.execute('INSERT INTO scan_runs(source,started_at,completed_at,coverage,found,written,failures,detail) VALUES(?,?,?,?,?,?,?,?)',
                              (source,t,now(),'verified_visible_catalogues',len(records),written,int(failures),str(detail)[:2000]))
        return written

    def sales_windows(self, product_id, when=None):
        """Observed negative inventory deltas, NOT orders. Reject incomplete history.
        Returns None when history cannot cover full requested period.
        """
        end=when or datetime.now().astimezone()
        rows=self.conn.execute('SELECT captured_at,stock,stock_delta FROM snapshots WHERE product_id=? ORDER BY captured_at,id',
                               (int(product_id),)).fetchall()
        if not rows:return {'24h':None,'7d':None,'30d':None}
        result={}
        for label,days in [('24h',1),('7d',7),('30d',30)]:
            start=end-timedelta(days=days)
            try:
                times=[datetime.fromisoformat(r['captured_at']) for r in rows]
            except ValueError:
                result[label]=None;continue
            # First observation must precede the window boundary, last one must
            # be reasonably recent; otherwise do not present an authoritative period.
            if times[0]>start or times[-1]<end-timedelta(hours=3):
                result[label]=None;continue
            result[label]=sum(max(0,-int(r['stock_delta'])) for r,t in zip(rows,times)
                              if t>=start and t<=end and r['stock_delta'] is not None)
        return result

    def project_sales(self,project_id):
        return {r['id']:self.sales_windows(r['id']) for r in self.project_products(project_id)}

    def close(self): self.conn.close()


def import_csv(store, path):
    """CSV columns: source,external_id,name,price_usd,stock,variant,url"""
    count=0; errors=[]
    with open(path,'r',encoding='utf-8-sig',newline='') as f:
        for i,row in enumerate(csv.DictReader(f),2):
            try:
                store.upsert(row.get('source','').upper(),row['external_id'],row['name'],row['price_usd'],row.get('stock'),row.get('variant',''),row.get('url',''))
                count+=1
            except Exception as e: errors.append(f'第{i}行：{e}')
    return count,errors


def fetch_fb_product(url, timeout=20):
    """Read individual public product page. Parsing is best effort, must verify before production use."""
    u=urlparse(url)
    if u.scheme!='https' or u.hostname not in ('fb1314.com','www.fb1314.com'):
        raise ValueError('仅允许 FB1314 HTTPS 商品链接')
    mid=re.search(r'/goods/(\d+)\.html',u.path)
    if not mid: raise ValueError('商品链接格式应为 /goods/数字.html')
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 InventoryManager/0.1','Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        html=resp.read(2_000_000).decode('utf-8','replace')
    text=unescape(re.sub(r'<[^>]+>',' ',re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',html,flags=re.I|re.S)))
    text=re.sub(r'\s+',' ',text)
    title_match=re.search(r'<h1[^>]*>(.*?)</h1>',html,re.I|re.S)
    name=unescape(re.sub('<[^>]+>','',title_match.group(1))).strip() if title_match else ''
    stock_match=re.search(r'库存\s*[:：]?\s*(\d+)',text)
    price_match=re.search(r'\$\s*(\d+(?:\.\d{1,4})?)',text)
    if not name or not price_match or not stock_match:
        raise ValueError('网页结构不匹配，无法可靠提取商品名称/价格/库存；未写入数据库')
    return {'source':'FB1314','external_id':mid.group(1),'name':name,'price':price_match.group(1),'stock':int(stock_match.group(1)),'url':url}
