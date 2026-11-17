"""Execute tasks on independent SQLite connection, safe for Tk background worker."""
from pathlib import Path
from core import Store
from browser_collect import browse_and_collect
from site_discovery import scan_site, discover_site_categories
from image_render import render_project
from telegram_sender import send_photo, unprotect_token


def scan_result_complete(stats, stop=None):
    """A scan is publishable only when every completeness signal is clean."""
    return bool(
        stats.get('listed', 0) > 0
        and not stats.get('truncated', False)
        and stats.get('failed', 0) == 0
        and stats.get('incomplete_cards', 0) == 0
        and not (stop and stop.is_set())
    )

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
            complete=scan_result_complete(stats,stop)
            written=store.ingest_category_scan(source,items,selected,complete,len(failed),
                                                '；'.join(failed[:12]))
            if not complete:
                # Surface incomplete scans as failed scheduled runs so the job history
                # records the error and operators do not mistake it for a successful cycle.
                raise RuntimeError(f'{source} 扫描不完整：识别 {stats["listed"]} 件，异常页面 {len(failed)}，待核实商品卡 {stats.get("incomplete_cards",0)}；正式数据库及库存快照未更新。诊断报告：{stats.get('diagnostic_report','')}')
            report=stats.get('diagnostic_report','')
            return (f'{source} 已更新 {written} 件；本次覆盖启用类目 {len(selected)} 个，异常 {len(failed)}。'
                    f'本次仅代表公开可见列表扫描结果，不代表网站隐藏/登录态库存完整。诊断报告：{report}')
        if job['kind'] in ('capture','publish'):
            pid=job['project_id'];rows=store.project_products(pid)
            if not rows:raise ValueError('项目没有商品，不能发布')
            name=store.conn.execute('SELECT name FROM projects WHERE id=?',(pid,)).fetchone()
            if not name:raise ValueError('项目不存在')
            periods=store.get_project_periods(pid)
            project_opts=store.conn.execute('SELECT include_out_of_stock FROM projects WHERE id=?',(pid,)).fetchone()
            paths=render_project(rows,name['name'],settings['screens_dir'],
                  settings.get('render_title','每日商品报价'),settings.get('render_footer','报价以最新库存为准'),
                  include_oos=bool(project_opts['include_out_of_stock']) if project_opts else True, sales_periods=periods,sales_by_product=store.project_sales(pid))
            if job['kind']=='capture':return f'成功生成 {len(paths)} 张报价图：{paths[0]}'
            token=unprotect_token(settings.get('tg_token_encrypted',''))
            if not token:raise ValueError('没有保存 Telegram Bot Token')
            # Resume multi-page publication safely after a partial Telegram failure.
            import uuid
            scheduled=job.get('next_run')
            batch_key=(f"job:{job.get('id')}:{scheduled}" if job.get('id') and scheduled
                       else f"manual:{uuid.uuid4().hex}")
            messages=[];skipped=[]
            for i,path in enumerate(paths):
                if store.publish_page_done(batch_key,i):
                    skipped.append(i+1)
                    continue
                caption=job['caption'] if i==0 else f'{name["name"]}（续 {i+1}/{len(paths)}）'
                try:
                    msg=send_photo(token,job['target'],path,caption)
                    store.record_publish_page(pid,job['target'],batch_key,i,'success',
                        detail='Telegram 已确认发送',job_id=job.get('id'),message_id=msg)
                    messages.append(msg)
                except Exception as exc:
                    store.record_publish_page(pid,job['target'],batch_key,i,'failed',
                        detail=str(exc),job_id=job.get('id'))
                    raise RuntimeError(f'第 {i+1}/{len(paths)} 张图片发送失败；此前成功页已记录，重试时会跳过成功页：{exc}') from exc
            return f'发布完成：共 {len(paths)} 页；本次发送 {len(messages)} 页；跳过已成功页 {len(skipped)} 页；消息ID {messages}'
        raise ValueError('未知任务类型')
    finally:store.close()
