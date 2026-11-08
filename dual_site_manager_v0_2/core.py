"""Offline-first inventory management core. No account credentials stored in SQLite."""
import csv
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone
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
        CREATE TABLE IF NOT EXISTS publish_log (
          id INTEGER PRIMARY KEY, project_id INTEGER, target TEXT, created_at TEXT,
          status TEXT, detail TEXT);
        CREATE INDEX IF NOT EXISTS idx_product_source ON products(source,status);
        CREATE INDEX IF NOT EXISTS idx_snapshots_product ON snapshots(product_id,captured_at);
        ''')
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
        if search: where.append('(name LIKE ? OR external_id LIKE ?)');params.extend(['%'+search+'%']*2)
        q = 'SELECT * FROM products' + (' WHERE '+' AND '.join(where) if where else '')+' ORDER BY updated_at DESC,id DESC'
        return self.conn.execute(q,params).fetchall()

    def set_status(self, ids, status):
        if status not in ('review','active','paused','excluded'): raise ValueError('状态错误')
        with self.conn:
            self.conn.executemany('UPDATE products SET status=? WHERE id=?',[(status,int(i)) for i in ids])

    def add_project(self,name):
        with self.conn:
            self.conn.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',(name.strip(),now()))

    def projects(self):
        return self.conn.execute('SELECT * FROM projects ORDER BY id').fetchall()

    def project_assign(self, project_id, product_ids):
        with self.conn:
            self.conn.executemany('INSERT OR IGNORE INTO project_products(project_id,product_id) VALUES (?,?)',[(project_id,int(p)) for p in product_ids])

    def project_products(self,project_id):
        return self.conn.execute('''SELECT p.*,pp.custom_usd FROM products p JOIN project_products pp ON pp.product_id=p.id WHERE pp.project_id=? ORDER BY pp.sort_order,p.id''',(project_id,)).fetchall()

    def set_project_price(self,project_id,product_id,price):
        with self.conn:
            self.conn.execute('UPDATE project_products SET custom_usd=? WHERE project_id=? AND product_id=?',
                (usd(price) if str(price).strip() else None,project_id,product_id))

    def history(self,product_id):
        return self.conn.execute('SELECT * FROM snapshots WHERE product_id=? ORDER BY id DESC LIMIT 500',(product_id,)).fetchall()

    def stats(self):
        result={}
        for source in SOURCES:
            r=self.conn.execute('SELECT COUNT(*) n, SUM(CASE WHEN status="review" THEN 1 ELSE 0 END) review FROM products WHERE source=?',(source,)).fetchone()
            result[source]={'count':r['n'],'review':r['review'] or 0}
        return result

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
