"""Execute tasks on independent SQLite connection, safe for Tk background worker."""
from pathlib import Path
from core import Store
from browser_collect import browse_and_collect
from site_discovery import scan_site, discover_site_categories
from image_render import render_project
from telegram_sender import send_photo, unprotect_token

def execute(job,db_path,settings,progress=None,stop=None):
    store=Store(db_path)
    root=Path(settings['data_dir']).parent
    source=job['source']
    try:
        if job['kind']=='categories':
            cats=discover_site_categories(source,root/'BrowserProfiles',root/'Diagnostics',
                                         headed=bool(settings.get('visible_browser',True)))
            store.register_categories(source,cats)
            if progress:progress({'stage':'类目目录已更新','categories':len(cats),'source':source})
            return f'{source} 发现 {len(cats)} 个候选分类，已列入待审核类目；请勾选要采集的分类。'
        if job['kind'] in ('discover','refresh'):
            selected=store.enabled_category_keys(source)
            if not selected:raise ValueError('尚未启用网站原始类目：请先进入「网站类目管理」发现并启用分类')
            items,failed,stats=scan_site(source,root/'BrowserProfiles',root/'Diagnostics',
                max_pages=int(settings.get('scan_limit',1200)),
                headed=bool(settings.get('visible_browser',True)),
                selected_categories=selected,progress=progress,stop=stop)
            complete=not stats['truncated'] and stats['listed']>0 and stats['failed']==0
            written=store.ingest_category_scan(source,items,selected,complete,len(failed),
                                                '；'.join(failed[:12]))
            if not complete:
                return f'{source} 扫描不完整：识别 {stats["listed"]} 件，异常 {len(failed)}，正式数据库未更新。详情见诊断文件。'
            return f'{source} 已更新 {written} 件；本次覆盖启用类目 {len(selected)} 个，异常 {len(failed)}。'
        if job['kind'] in ('capture','publish'):
            pid=job['project_id'];rows=store.project_products(pid)
            if not rows:raise ValueError('项目没有商品，不能发布')
            name=store.conn.execute('SELECT name FROM projects WHERE id=?',(pid,)).fetchone()
            if not name:raise ValueError('项目不存在')
            periods=store.get_project_periods(pid)
            paths=render_project(rows,name['name'],settings['screens_dir'],
                  settings.get('render_title','每日商品报价'),settings.get('render_footer','报价以最新库存为准'),
                  sales_periods=periods,sales_by_product=store.project_sales(pid))
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
