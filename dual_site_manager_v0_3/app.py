"""Windows desktop prototype v0.2: Tkinter, no dependencies for database and CSV."""
import json
import os
import shutil
import sqlite3
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime
from core import Store, import_csv, now
from browser_collect import browse_and_collect, validate_link
from task_runner import execute
from telegram_sender import protect_token

APP='双站商品管理中心 v0.3 · 全站发现/自动发布'
CONFIG=Path(os.getenv('APPDATA',str(Path.home()))) / 'DualSiteInventory' / 'settings.json'
DEFAULT_ROOT=Path.home()/'Documents'/'DualSiteInventory'

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP);self.geometry('1180x760');self.minsize(950,600)
        self.settings=self._read_settings()
        self.store=Store(Path(self.settings['data_dir'])/'inventory.sqlite3')
        self.selected_project={}
        self.active_job=False
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        ttk.Label(self,text='双网站商品采集 · 库存监控 · 项目定价 · 截图管理',font=('Microsoft YaHei UI',17,'bold')).grid(row=0,column=0,padx=16,pady=12,sticky='w')
        self.tabs=ttk.Notebook(self);self.tabs.grid(row=1,column=0,sticky='nsew',padx=12,pady=4)
        self.status=tk.StringVar(value='就绪 · 尚未执行真实网站采集')
        self._build_overview();self._build_goods();self._build_projects();self._build_collect();self._build_capture();self._build_automation();self._build_settings()
        ttk.Label(self,textvariable=self.status,anchor='w').grid(row=2,column=0,sticky='ew',padx=15,pady=8)
        self.refresh_all();self.protocol('WM_DELETE_WINDOW',self._exit)
        self.after(20000,self._poll_jobs)

    def _read_settings(self):
        defaults={'data_dir':str(DEFAULT_ROOT/'Database'),'screens_dir':str(DEFAULT_ROOT/'Screenshots'),
                  'backup_dir':str(DEFAULT_ROOT/'Backups'),'font':11,'fb_interval':30,'ceo_interval':30,
                  'fb_urls':[],'ceo_urls':[],'scan_limit':1200,'visible_browser':True,'tg_token_encrypted':'','render_title':'每日商品报价','render_footer':'价格库存以最新查询为准'}
        if CONFIG.exists():
            try:
                incoming=json.loads(CONFIG.read_text('utf-8'))
                defaults.update({k:v for k,v in incoming.items() if k in defaults})
            except (OSError,ValueError):pass
        return defaults

    def _save_settings(self):
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        tmp=CONFIG.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),'utf-8')
        os.replace(tmp,CONFIG)

    def _frame(self,label):
        root=ttk.Frame(self.tabs,padding=14);self.tabs.add(root,text=label)
        root.columnconfigure(0,weight=1);root.rowconfigure(1,weight=1)
        return root

    def _table(self,parent,columns,widths=None):
        box=ttk.Frame(parent);box.grid(row=1,column=0,sticky='nsew',pady=6)
        box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        t=ttk.Treeview(box,columns=columns,show='headings',selectmode='extended')
        for i,c in enumerate(columns):t.heading(c,text=c);t.column(c,width=(widths or {}).get(c,120),anchor='w')
        t.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(box,orient='vertical',command=t.yview);sy.grid(row=0,column=1,sticky='ns');t.configure(yscrollcommand=sy.set)
        return t

    def _build_overview(self):
        f=self._frame('总览');f.rowconfigure(1,weight=0)
        self.overview=tk.Text(f,height=16,font=('Consolas',12),state='disabled',wrap='word')
        self.overview.grid(row=1,column=0,sticky='nsew',pady=12)
        ttk.Label(f,text='主入口请使用「全站与自动化」：自动发现商品、定时更新库存、定时生成项目图片并通过 Telegram Bot 发布。网页适配仍需真实站点验证。',wraplength=900).grid(row=2,column=0,sticky='w')

    def _build_goods(self):
        f=self._frame('商品数据库');top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew')
        self.source_var=tk.StringVar(value='全部');self.state_var=tk.StringVar(value='全部');self.search_var=tk.StringVar()
        ttk.Label(top,text='来源').pack(side='left');ttk.Combobox(top,textvariable=self.source_var,values=['全部','FB1314','CEOACC'],state='readonly',width=10).pack(side='left',padx=5)
        ttk.Label(top,text='状态').pack(side='left');ttk.Combobox(top,textvariable=self.state_var,values=['全部','review','active','paused','excluded'],state='readonly',width=11).pack(side='left',padx=5)
        ttk.Entry(top,textvariable=self.search_var,width=25).pack(side='left',padx=8)
        ttk.Button(top,text='筛选 / 刷新',command=self.refresh_goods).pack(side='left',padx=4)
        ttk.Button(top,text='导入 CSV',command=self.import_csv_file).pack(side='left',padx=4)
        self.goods=self._table(f,['ID','网站','网站商品ID','规格','名称','USD 原价','库存','状态','更新时间'],{'名称':260,'网站商品ID':110,'更新时间':170})
        buttons=ttk.Frame(f);buttons.grid(row=2,column=0,sticky='w',pady=7)
        for text,status in [('启用采集','active'),('暂停采集','paused'),('永久排除','excluded'),('待审核','review')]:
            ttk.Button(buttons,text=text,command=lambda s=status:self.change_status(s)).pack(side='left',padx=5)
        ttk.Button(buttons,text='查看库存历史',command=self.show_history).pack(side='left',padx=5)

    def _build_projects(self):
        f=self._frame('项目与定价');top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew')
        ttk.Button(top,text='新建项目',command=self.create_project).pack(side='left',padx=4)
        self.project_var=tk.StringVar();self.project_box=ttk.Combobox(top,textvariable=self.project_var,state='readonly',width=30)
        self.project_box.pack(side='left',padx=8);self.project_box.bind('<<ComboboxSelected>>',lambda e:self.refresh_projects())
        ttk.Button(top,text='将商品页所选商品加入本项目',command=self.assign_products).pack(side='left',padx=4)
        ttk.Button(top,text='设置选中商品的项目售价',command=self.set_price).pack(side='left',padx=4)
        self.project_table=self._table(f,['ID','网站','商品名称','商品规格','网站 USD','项目 USD','库存'],{'商品名称':320})

    def _build_collect(self):
        f=self._frame('网站采集');f.rowconfigure(1,weight=0)
        ttk.Label(f,text='此页仅作为单链接故障诊断；全站发现请使用「全站与自动化」页面。不会尝试绕过网站安全验证。',wraplength=1000).grid(row=0,column=0,sticky='w')
        body=ttk.Frame(f);body.grid(row=1,column=0,sticky='nsew',pady=8)
        body.columnconfigure(0,weight=1)
        ttk.Label(body,text='FB1314 商品详情链接（每行一条）').grid(row=0,column=0,sticky='w')
        self.fb_links=tk.Text(body,height=5)
        self.fb_links.grid(row=1,column=0,sticky='ew');self.fb_links.insert('1.0','\n'.join(self.settings['fb_urls']))
        ttk.Button(body,text='浏览器采集 FB1314',command=lambda:self.collect_site('FB1314')).grid(row=2,column=0,sticky='w',pady=5)
        ttk.Separator(body).grid(row=3,column=0,sticky='ew',pady=10)
        ttk.Label(body,text='CEOACC 商品详情链接（每行一条）· 不使用 API / API Key').grid(row=4,column=0,sticky='w')
        self.ceo_links=tk.Text(body,height=5)
        self.ceo_links.grid(row=5,column=0,sticky='ew');self.ceo_links.insert('1.0','\n'.join(self.settings.get('ceo_urls',[])))
        ttk.Button(body,text='浏览器采集 CEOACC',command=lambda:self.collect_site('CEOACC')).grid(row=6,column=0,sticky='w',pady=5)
        ttk.Label(body,text='按钮默认打开可见 Chromium。FB1314 检测「继续 Continue」；CEOACC 检测「不再显示」/「关闭」。CEOACC 暂仅支持含完整 USD JSON-LD 商品结构化数据的页面；否则只保存诊断截图，不会凭空猜库存。',wraplength=960).grid(row=7,column=0,sticky='w',pady=10)

    def _build_capture(self):
        f=self._frame('截图输出');f.rowconfigure(1,weight=0)
        body=ttk.Frame(f);body.grid(row=1,column=0,sticky='ew',pady=10)
        ttk.Label(body,text='选择项目（在「项目与定价」创建并添加商品后生成）：').grid(row=0,column=0,sticky='w')
        self.render_project=tk.StringVar();self.render_box=ttk.Combobox(body,textvariable=self.render_project,state='readonly',width=35)
        self.render_box.grid(row=0,column=1,sticky='w',padx=10)
        ttk.Label(body,text='截图标题：').grid(row=1,column=0,sticky='w',pady=8)
        self.render_title=tk.StringVar(value=self.settings['render_title']);ttk.Entry(body,textvariable=self.render_title,width=55).grid(row=1,column=1,sticky='w')
        ttk.Label(body,text='底部文案：').grid(row=2,column=0,sticky='w',pady=8)
        self.render_footer=tk.StringVar(value=self.settings['render_footer']);ttk.Entry(body,textvariable=self.render_footer,width=55).grid(row=2,column=1,sticky='w')
        ttk.Button(body,text='生成项目 PNG 报价图片',command=self.export_png).grid(row=3,column=1,sticky='w',pady=12)
        ttk.Label(body,text='图片渲染使用 Pillow；自动截图与 Telegram 发布任务请在「全站与自动化」配置。').grid(row=4,column=0,columnspan=2,sticky='w')

    def _build_automation(self):
        f=self._frame('全站与自动化')
        top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew',pady=5)
        ttk.Label(top,text='一键扫描两个网站公开分类、分页和商品详情，自动登记链接；新商品先进入待审核。',wraplength=900).pack(anchor='w')
        btns=ttk.Frame(top);btns.pack(anchor='w',pady=6)
        ttk.Button(btns,text='立即全站扫描 FB1314',command=lambda:self.run_manual('discover','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='立即全站扫描 CEOACC',command=lambda:self.run_manual('discover','CEOACC')).pack(side='left',padx=3)
        ttk.Button(btns,text='更新 FB1314 已启用商品',command=lambda:self.run_manual('refresh','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='更新 CEOACC 已启用商品',command=lambda:self.run_manual('refresh','CEOACC')).pack(side='left',padx=3)
        form=ttk.LabelFrame(f,text='新增定时任务',padding=8);form.grid(row=1,column=0,sticky='ew',pady=6)
        self.job_kind=tk.StringVar(value='discover');self.job_source=tk.StringVar(value='FB1314')
        self.job_interval=tk.StringVar(value='360');self.job_target=tk.StringVar();self.job_caption=tk.StringVar(value='每日商品报价 · 库存价格以最新数据为准')
        self.job_project=tk.StringVar()
        ttk.Label(form,text='任务类型').grid(row=0,column=0,sticky='w')
        ttk.Combobox(form,textvariable=self.job_kind,values=['discover','refresh','capture','publish'],state='readonly',width=13).grid(row=0,column=1,padx=5)
        ttk.Label(form,text='网站').grid(row=0,column=2)
        ttk.Combobox(form,textvariable=self.job_source,values=['FB1314','CEOACC'],state='readonly',width=11).grid(row=0,column=3,padx=5)
        ttk.Label(form,text='间隔(分钟)').grid(row=0,column=4)
        ttk.Entry(form,textvariable=self.job_interval,width=9).grid(row=0,column=5,padx=5)
        ttk.Label(form,text='发布项目').grid(row=1,column=0,sticky='w',pady=6)
        self.auto_project=ttk.Combobox(form,textvariable=self.job_project,state='readonly',width=25)
        self.auto_project.grid(row=1,column=1,columnspan=2,sticky='w')
        ttk.Label(form,text='Telegram 群组/频道ID').grid(row=1,column=3,sticky='e')
        ttk.Entry(form,textvariable=self.job_target,width=27).grid(row=1,column=4,columnspan=2,sticky='w')
        ttk.Label(form,text='图片文案').grid(row=2,column=0,sticky='w')
        ttk.Entry(form,textvariable=self.job_caption,width=74).grid(row=2,column=1,columnspan=5,sticky='ew')
        ttk.Button(form,text='保存任务',command=self.create_job).grid(row=3,column=1,sticky='w',pady=9)
        ttk.Button(form,text='保存 Telegram Bot Token',command=self.configure_bot).grid(row=3,column=2,columnspan=3,sticky='w')
        ttk.Label(form,text='发布须先将 Bot 加入目标群组/频道并授予发消息权限。此版本使用 Bot API，不支持个人账号登录。',wraplength=890).grid(row=4,column=0,columnspan=6,sticky='w')
        f.rowconfigure(2,weight=1)
        self.job_table=self._table_at(f,2,['ID','类型','网站/项目','分钟','目标','下次运行','最近错误'])
        ctl=ttk.Frame(f);ctl.grid(row=3,column=0,sticky='w',pady=4)
        ttk.Button(ctl,text='立即执行选中任务',command=self.run_selected_job).pack(side='left',padx=3)
        ttk.Button(ctl,text='删除选中任务',command=self.delete_selected_job).pack(side='left',padx=3)
        ttk.Button(ctl,text='刷新列表',command=self.refresh_jobs).pack(side='left',padx=3)

    def _table_at(self,parent,row,columns):
        box=ttk.Frame(parent);box.grid(row=row,column=0,sticky='nsew',pady=3)
        box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        t=ttk.Treeview(box,columns=columns,show='headings',selectmode='browse')
        for c in columns:t.heading(c,text=c);t.column(c,width=110 if c!='最近错误' else 260)
        t.grid(row=0,column=0,sticky='nsew')
        ttk.Scrollbar(box,orient='vertical',command=t.yview).grid(row=0,column=1,sticky='ns')
        return t

    def refresh_jobs(self):
        if not hasattr(self,'job_table'):return
        import datetime as dt
        self.job_table.delete(*self.job_table.get_children())
        values=[f'{p["id"]} · {p["name"]}' for p in self.store.projects()]
        self.auto_project['values']=values
        if values and self.job_project.get() not in values:self.job_project.set(values[0])
        for j in self.store.jobs():
            scope=j['source'] or ('项目 '+str(j['project_id']))
            when=dt.datetime.fromtimestamp(j['next_run']).strftime('%m-%d %H:%M')
            self.job_table.insert('','end',iid=str(j['id']),values=(j['id'],j['kind'],scope,j['interval_minutes'],j['target'],when,j['last_error'][:80]))

    def configure_bot(self):
        token=simpledialog.askstring('Telegram Bot Token','请输入 BotFather 提供的 Bot Token（将以 Windows 用户加密方式保存）：',show='*',parent=self)
        if not token:return
        try:
            self.settings['tg_token_encrypted']=protect_token(token.strip());self._save_settings()
            messagebox.showinfo('已保存','Bot Token 已使用 Windows DPAPI 加密保存。')
        except Exception as exc:messagebox.showerror('保存失败',str(exc))

    def create_job(self):
        try:
            kind=self.job_kind.get();source=self.job_source.get() if kind not in ('capture','publish') else ''
            pid=self._project_id(self.job_project.get()) if kind in ('capture','publish') else None
            if kind in ('capture','publish') and not pid:raise ValueError('截图/发布任务需要选择一个项目')
            if kind=='publish' and not self.job_target.get().strip():raise ValueError('发布任务需要目标频道/群组')
            self.store.add_job(kind+' '+(source or str(pid)),kind,int(self.job_interval.get()),source,pid,
              self.job_target.get().strip() if kind=='publish' else '',self.job_caption.get() if kind=='publish' else '')
            self.refresh_jobs();self.status.set('自动任务已添加')
        except Exception as exc:messagebox.showerror('创建任务失败',str(exc))

    def run_manual(self,kind,source):
        job={'kind':kind,'source':source,'project_id':None,'target':'','caption':''}
        self._run_automation(job)

    def run_selected_job(self):
        ids=self.job_table.selection()
        if not ids:return messagebox.showinfo('提示','先选择一条任务')
        job=next((dict(j) for j in self.store.jobs() if str(j['id'])==ids[0]),None)
        if job:self._run_automation(job)

    def delete_selected_job(self):
        ids=self.job_table.selection()
        if not ids:return
        if messagebox.askyesno('确认','删除选中的定时任务？'):
            self.store.delete_job(ids[0]);self.refresh_jobs()

    def _run_automation(self,job):
        if self.active_job:return messagebox.showwarning('任务正在运行','一次仅允许运行一个采集或发布任务')
        self.active_job=True;self.status.set('正在执行 '+job['kind']+'...')
        settings=dict(self.settings);db_path=str(self.store.path)
        def work():
            error=''
            try:result=execute(job,db_path,settings)
            except Exception as exc:error=str(exc);result='任务失败：'+error
            self.after(0,lambda:self._finish_automation(job,result,error))
        threading.Thread(target=work,daemon=True).start()

    def _finish_automation(self,job,result,error):
        self.active_job=False
        if job.get('id'):self.store.mark_job(job['id'],error)
        self.refresh_all();self.refresh_jobs();self.status.set(result)
        if not job.get('_scheduled'):
            if error:messagebox.showerror('自动任务失败',result)
            else:messagebox.showinfo('任务结果',result)

    def _poll_jobs(self):
        try:
            import time
            if not self.active_job:
                due=next((dict(j) for j in self.store.jobs() if j['enabled'] and j['next_run']<=time.time()),None)
                if due:
                    due['_scheduled']=True
                    self._run_automation(due)
        finally:
            self.after(30000,self._poll_jobs)

    def _build_settings(self):
        f=self._frame('系统与文件夹');f.rowconfigure(1,weight=0)
        body=ttk.Frame(f);body.grid(row=1,column=0,sticky='ew',pady=14);body.columnconfigure(1,weight=1)
        self.paths={}
        for idx,(key,name) in enumerate([('screens_dir','截图保存目录'),('data_dir','数据库保存目录'),('backup_dir','备份保存目录')]):
            ttk.Label(body,text=name).grid(row=idx,column=0,sticky='w',padx=4,pady=12)
            v=tk.StringVar(value=self.settings[key]);self.paths[key]=v
            ttk.Entry(body,textvariable=v).grid(row=idx,column=1,sticky='ew',padx=8)
            ttk.Button(body,text='浏览文件夹',command=lambda x=v:self.choose_dir(x)).grid(row=idx,column=2,padx=3)
        ttk.Label(body,text='界面字体大小').grid(row=3,column=0,sticky='w',padx=4,pady=12)
        self.font_size=tk.StringVar(value=str(self.settings['font']))
        ttk.Combobox(body,textvariable=self.font_size,values=['10','11','12','14','16','18'],width=10,state='readonly').grid(row=3,column=1,sticky='w')
        ttk.Button(body,text='保存路径和设置（数据库迁移需关闭后重新打开）',command=self.save_paths).grid(row=4,column=1,sticky='w',pady=14)
        ttk.Button(body,text='立即备份数据库',command=self.backup_database).grid(row=5,column=1,sticky='w')
        ttk.Label(body,text='单次扫描页面上限').grid(row=6,column=0,sticky='w',padx=4,pady=8)
        self.scan_limit_var=tk.StringVar(value=str(self.settings.get('scan_limit',1200)))
        ttk.Entry(body,textvariable=self.scan_limit_var,width=10).grid(row=6,column=1,sticky='w')
        self.visible_browser_var=tk.BooleanVar(value=bool(self.settings.get('visible_browser',True)))
        ttk.Checkbutton(body,text='显示网页采集浏览器（用于查看公告和手动安全验证）',variable=self.visible_browser_var).grid(row=7,column=1,sticky='w')
        ttk.Label(body,text='安全说明：数据库正在运行时不直接复制 SQLite 主文件；使用 SQLite 在线备份。切换数据库目录会先复制有效快照，重启后生效。').grid(row=8,column=0,columnspan=3,sticky='w',pady=12)

    def refresh_all(self):
        self.refresh_goods();self.refresh_projects();self.refresh_overview();self.refresh_jobs()

    def refresh_overview(self):
        stats=self.store.stats();lines=['双站商品监控概览','='*42]
        for name,d in stats.items():lines.append(f'{name:10}  商品数：{d["count"]:>5}   待审核新品：{d["review"]:>5}')
        lines.extend(['','数据库位置：'+str(self.store.path),'截图目录：'+self.settings['screens_dir'],
                      '备份目录：'+self.settings['backup_dir'],'','版本：v0.2 原型，未验证的定时采集/Telegram 发布暂不启用。'])
        self.overview.configure(state='normal');self.overview.delete('1.0','end');self.overview.insert('1.0','\n'.join(lines));self.overview.configure(state='disabled')

    def refresh_goods(self):
        self.goods.delete(*self.goods.get_children())
        source=self.source_var.get();state=self.state_var.get()
        for p in self.store.products('' if source=='全部' else source,'' if state=='全部' else state,self.search_var.get().strip()):
            self.goods.insert('', 'end',iid=str(p['id']),values=(p['id'],p['source'],p['external_id'],p['variant'],p['name'],p['raw_usd'],p['stock'] if p['stock'] is not None else '未知',p['status'],p['updated_at']))

    def change_status(self,status):
        ids=self.goods.selection()
        if not ids:return messagebox.showinfo('提示','请先选择一个或多个商品')
        self.store.set_status(ids,status);self.refresh_all();self.status.set(f'已修改 {len(ids)} 件商品状态为 {status}')

    def show_history(self):
        ids=self.goods.selection()
        if not ids:return messagebox.showinfo('提示','请先选中一个商品')
        top=tk.Toplevel(self);top.title('商品库存与价格历史');top.geometry('800x430')
        t=ttk.Treeview(top,columns=['时间','USD','库存','库存变化','价格变化'],show='headings')
        for col in ['时间','USD','库存','库存变化','价格变化']:t.heading(col,text=col);t.column(col,width=140)
        t.pack(fill='both',expand=True)
        for r in self.store.history(int(ids[0])):t.insert('','end',values=(r['captured_at'],r['raw_usd'],r['stock'],r['stock_delta'],r['price_delta']))

    def import_csv_file(self):
        path=filedialog.askopenfilename(filetypes=[('CSV 文件','*.csv')])
        if not path:return
        try:
            n,errors=import_csv(self.store,path);self.refresh_all()
            messagebox.showinfo('导入结果',f'成功 {n} 件\n失败 {len(errors)} 件'+ ('\n'+'\n'.join(errors[:10]) if errors else ''))
        except Exception as e:messagebox.showerror('导入失败',str(e))

    def _project_id(self,selection=None):
        s=(selection or self.project_var.get()).split(' · ',1)[0]
        try:return int(s)
        except ValueError:return None

    def refresh_projects(self):
        projects=self.store.projects();values=[f'{p["id"]} · {p["name"]}' for p in projects]
        self.project_box['values']=values;self.render_box['values']=values
        if values and self.project_var.get() not in values:self.project_var.set(values[0])
        if values and self.render_project.get() not in values:self.render_project.set(values[0])
        self.project_table.delete(*self.project_table.get_children())
        pid=self._project_id()
        if pid:
            for r in self.store.project_products(pid):
                self.project_table.insert('','end',iid=str(r['id']),values=(r['id'],r['source'],r['name'],r['variant'],r['raw_usd'],r['custom_usd'] or r['raw_usd'],r['stock'] if r['stock'] is not None else '未知'))

    def create_project(self):
        name=simpledialog.askstring('新建项目','输入项目名称：',parent=self)
        if not name:return
        try:self.store.add_project(name);self.refresh_projects();self.refresh_jobs()
        except sqlite3.IntegrityError:messagebox.showerror('重复','已存在同名项目')

    def assign_products(self):
        pid=self._project_id();ids=self.goods.selection()
        if not pid or not ids:return messagebox.showinfo('提示','先选择项目，再前往商品数据库选中商品')
        self.store.project_assign(pid,ids);self.refresh_projects();self.status.set(f'已添加 {len(ids)} 件商品到项目')

    def set_price(self):
        pid=self._project_id();ids=self.project_table.selection()
        if not pid or not ids:return messagebox.showinfo('提示','请选择项目中的商品')
        price=simpledialog.askstring('项目独立定价','请输入 USD 价格，留空则使用网站原价：',parent=self)
        if price is None:return
        try:
            for product_id in ids:self.store.set_project_price(pid,product_id,price)
            self.refresh_projects()
        except ValueError as e:messagebox.showerror('价格错误',str(e))

    def _async(self,func,label):
        if self.active_job:return messagebox.showwarning('任务运行中','请等待当前任务完成')
        self.active_job=True;self.status.set(label+' ...')
        def run():
            try:result=func();self.after(0,lambda:self._job_finished(result,None))
            except Exception as e:self.after(0,lambda error=str(e):self._job_finished(None,error))
        threading.Thread(target=run,daemon=True).start()

    def _job_finished(self,result,error):
        self.active_job=False;self.refresh_all()
        if error:self.status.set('任务失败：'+error);messagebox.showerror('采集失败',error)
        else:self.status.set(str(result));messagebox.showinfo('执行结果',str(result))

    def collect_site(self,source):
        widget=self.fb_links if source=='FB1314' else self.ceo_links
        links=[v.strip() for v in widget.get('1.0','end').splitlines() if v.strip()]
        if not links:return messagebox.showinfo('提示','请先填写对应网站商品详情链接')
        try:
            for link in links: validate_link(source,link)
        except ValueError as e:
            return messagebox.showerror('链接检查失败',str(e))
        self.settings['fb_urls' if source=='FB1314' else 'ceo_urls']=links
        self._save_settings()
        known={r['url'] for r in self.store.products(source) if r['status'] in ('paused','excluded') and r['url']}
        selected=[link for link in links if link not in known]
        if not selected:return messagebox.showinfo('提示','所选商品全部已暂停或永久排除')
        def fetch_only():
            root=Path(self.settings['data_dir']).parent
            products,failed,events=browse_and_collect(source,selected,root/'BrowserProfiles',root/'Diagnostics',headed=True)
            return products,failed,events
        self._async_fetch(fetch_only,source+' 浏览器采集')

    def _async_fetch(self,func,label):
        if self.active_job:return messagebox.showwarning('任务运行中','当前采集尚未完成')
        self.active_job=True;self.status.set(label+' ...')
        def run():
            try:
                items,failed,events=func()
                self.after(0,lambda:self._apply_results(items,failed,label,events))
            except Exception as e:
                self.after(0,lambda error=str(e):self._job_finished(None,error))
        threading.Thread(target=run,daemon=True).start()

    def _apply_results(self,items,failed,label,events=None):
        n=0
        for item in items:
            try:
                existing=self.store.conn.execute('SELECT status FROM products WHERE source=? AND external_id=? AND variant=?',
                    (item['source'],str(item['external_id']),str(item.get('variant') or ''))).fetchone()
                if existing and existing['status'] in ('paused','excluded'):
                    continue
                self.store.upsert(**item);n+=1
            except Exception as e:failed.append(f'{item.get("external_id")}: {e}')
        self.active_job=False;self.refresh_all()
        outcome=f'{label}：成功更新 {n} 个商品/规格，失败 {len(failed)} 个。'+ ('\n'+'\n'.join((events or [])[:8]) if events else '') + ('\n'+'\n'.join(failed[:8]) if failed else '')
        self.status.set(outcome);messagebox.showinfo('采集结果',outcome)

    def export_png(self):
        pid=self._project_id(self.render_project.get())
        if not pid:return messagebox.showinfo('提示','请先创建项目')
        records=self.store.project_products(pid)
        if not records:return messagebox.showinfo('提示','项目没有商品')
        try:
            from PIL import Image,ImageDraw,ImageFont
            from PIL.ImageFont import truetype
        except ImportError:
            return messagebox.showerror('缺少 Pillow','运行 pip install Pillow 后可生成 PNG 图片')
        dest=Path(self.settings['screens_dir']);dest.mkdir(parents=True,exist_ok=True)
        def font(sz,bold=False):
            for path in ([r'C:\Windows\Fonts\msyhbd.ttc',r'C:\Windows\Fonts\msyh.ttc'] if bold else [r'C:\Windows\Fonts\msyh.ttc']):
                try:return truetype(path,sz)
                except OSError:pass
            return ImageFont.load_default()
        lineh=47;height=170+len(records)*lineh+80;img=Image.new('RGB',(1000,height),'#111c2b')
        d=ImageDraw.Draw(img)
        title=self.render_title.get() or '商品报价';footer=self.render_footer.get()
        d.text((32,28),title,font=font(36,True),fill='#f6f8fb')
        d.text((32,90),'商品名称',font=font(20,True),fill='#aac1d7')
        d.text((700,90),'价格 (USD)',font=font(20,True),fill='#aac1d7')
        d.text((880,90),'库存',font=font(20,True),fill='#aac1d7')
        d.line((30,126,970,126),fill='#47627e',width=2)
        for i,r in enumerate(records):
            y=142+i*lineh
            label=(r['name']+' '+r['variant'])[:38]
            d.text((32,y),label,font=font(20),fill='#eef3f8')
            d.text((705,y),'$'+(r['custom_usd'] or r['raw_usd']),font=font(21,True),fill='#ffd489')
            d.text((880,y),str(r['stock']) if r['stock'] is not None else '未知',font=font(20),fill='#9be2c0')
            d.line((30,y+36,970,y+36),fill='#304155')
        d.text((32,height-64),footer[:70],font=font(19),fill='#aebdd0')
        self.settings['render_title']=title;self.settings['render_footer']=footer;self._save_settings()
        fname=f'项目{pid}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png';path=dest/fname
        img.save(path)
        self.status.set('已生成：'+str(path));messagebox.showinfo('图片生成成功',str(path))

    def choose_dir(self,var):
        path=filedialog.askdirectory(initialdir=var.get() if Path(var.get()).exists() else str(Path.home()))
        if path:var.set(path)

    def save_paths(self):
        new={k:v.get().strip() for k,v in self.paths.items()}
        try:
            for value in new.values():
                if not value:raise ValueError('目录不可为空')
                folder=Path(value);folder.mkdir(parents=True,exist_ok=True)
                with open(folder/'.write_test','w',encoding='utf-8') as f:f.write('ok')
                (folder/'.write_test').unlink()
            if Path(new['data_dir']).resolve()!=self.store.path.parent.resolve():
                target=Path(new['data_dir'])/'inventory.sqlite3'
                if target.exists():raise ValueError('新数据库目录已有 inventory.sqlite3，禁止覆盖')
                backup=sqlite3.connect(str(target))
                try:self.store.conn.backup(backup)
                finally:backup.close()
                messagebox.showinfo('迁移成功','数据库已安全复制到新目录。请重启程序，后续更新写入新目录。原数据库保留作备份。')
            self.settings.update(new)
            self.settings['font']=int(self.font_size.get())
            self.settings['scan_limit']=int(self.scan_limit_var.get())
            if not 10<=self.settings['scan_limit']<=20000:raise ValueError('扫描页面上限应为 10-20000')
            self.settings['visible_browser']=self.visible_browser_var.get()
            self._save_settings();self.refresh_overview();self.status.set('设置已保存，字体变更重启生效')
        except Exception as e:messagebox.showerror('设置失败',str(e))

    def backup_database(self):
        try:
            path=Path(self.paths['backup_dir'].get());path.mkdir(parents=True,exist_ok=True)
            target=path/('inventory_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3')
            backup=sqlite3.connect(str(target))
            try:self.store.conn.backup(backup)
            finally:backup.close()
            self.status.set('备份完成：'+str(target));messagebox.showinfo('备份成功',str(target))
        except Exception as e:messagebox.showerror('备份失败',str(e))

    def _exit(self):
        self.store.close();self.destroy()

if __name__=='__main__':
    Application().mainloop()
