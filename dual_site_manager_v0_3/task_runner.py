"""Execute tasks on independent SQLite connection, safe for Tk background worker."""
from pathlib import Path
from core import Store
from browser_collect import browse_and_collect
from site_discovery import scan_site
from image_render import render_project
from telegram_sender import send_photo, unprotect_token

def execute(job,db_path,settings,progress=None):
    store=Store(db_path)
    root=Path(settings['data_dir']).parent
    source=job['source']
    try:
        if job['kind']=='discover':
            items,failed,stats=scan_site(source,root/'BrowserProfiles',root/'Diagnostics',
               max_pages=int(settings.get('scan_limit',1200)),headed=bool(settings.get('visible_browser',True)),progress=progress)
            ok=0
            for item in items:
                old=store.conn.execute('SELECT status FROM products WHERE source=? AND external_id=? AND variant=?',
                    (item['source'],str(item['external_id']),str(item.get('variant','')))).fetchone()
                if old and old['status'] in ('paused','excluded'):continue
                try:store.upsert(**item);ok+=1
                except Exception as exc:failed.append(str(exc))
            import datetime
            log_dir=root/'ScanLogs';log_dir.mkdir(parents=True,exist_ok=True)
            (log_dir/f'{source}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.txt').write_text('\n'.join(failed),encoding='utf-8')
            return f'{source} 发现扫描：访问页面 {stats["visited"]}，写入 {ok}，失败 {len(failed)}，扫描未完成={stats["truncated"]}。'+ (' 错误示例：'+ '; '.join(failed[:2]) if failed else '')
        if job['kind']=='refresh':
            urls=list(dict.fromkeys(r['url'] for r in store.products(source,'active') if r['url']))
            if not urls:return '没有已启用且含链接的商品'
            items,failed,_=browse_and_collect(source,urls,root/'BrowserProfiles',root/'Diagnostics',headed=bool(settings.get('visible_browser',True)))
            ok=0
            for item in items:
                row=store.conn.execute('SELECT status FROM products WHERE source=? AND external_id=? AND variant=?',
                   (item['source'],str(item['external_id']),str(item.get('variant','')))).fetchone()
                if row and row['status']=='active':store.upsert(**item);ok+=1
            return f'已刷新 {ok} 件，有 {len(failed)} 件失败：'+ '; '.join(failed[:2])
        if job['kind'] in ('capture','publish'):
            pid=job['project_id'];rows=store.project_products(pid)
            if not rows:raise ValueError('项目没有商品，不能发布')
            name=store.conn.execute('SELECT name FROM projects WHERE id=?',(pid,)).fetchone()
            if not name:raise ValueError('项目不存在')
            paths=render_project(rows,name['name'],settings['screens_dir'],
                  settings.get('render_title','每日商品报价'),settings.get('render_footer','报价以最新库存为准'))
            if job['kind']=='capture':return f'成功生成 {len(paths)} 张报价图：{paths[0]}'
            token=unprotect_token(settings.get('tg_token_encrypted',''))
            if not token:raise ValueError('没有保存 Telegram Bot Token')
            messages=[]
            for i,path in enumerate(paths):
                caption=job['caption'] if i==0 else f'{name["name"]}（续 {i+1}/{len(paths)}）'
                msg=send_photo(token,job['target'],path,caption)
                messages.append(msg)
            with store.conn:
                store.conn.execute('INSERT INTO publish_log(project_id,target,created_at,status,detail) VALUES(?,?,?,?,?)',
                    (pid,job['target'],__import__('core').now(),'success',str(messages)))
            return f'成功发送 {len(messages)} 张图片，消息ID {messages}'
        raise ValueError('未知任务类型')
    finally:store.close()
