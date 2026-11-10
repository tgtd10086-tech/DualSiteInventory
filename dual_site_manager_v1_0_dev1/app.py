"""Windows desktop prototype v0.2: Tkinter, no dependencies for database and CSV."""
import json
import queue
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

APP='黑盒铺子 · 双站商品管理中心 v1.0 开发验证版'
KIND_ZH={'categories':'网站原始类目发现','discover':'选定类目定时采集','refresh':'选定类目库存刷新','capture':'项目定时截图','publish':'Telegram 定时发布'}
ZH_KIND={v:k for k,v in KIND_ZH.items()}

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
        self.stop_scan=threading.Event()
        self.progress_messages=queue.Queue()
        self.configure(bg='#f3f7fc')
        self._setup_theme()
        self.columnconfigure(1,weight=1);self.rowconfigure(1,weight=1)
        header=tk.Frame(self,bg='#ffffff',height=64,highlightbackground='#e0e9f5',highlightthickness=1)
        header.grid(row=0,column=0,columnspan=2,sticky='ew');header.grid_propagate(False)
        tk.Label(header,text='◆  黑盒铺子   BlackBox Shop',fg='#173154',bg='#ffffff',font=('Microsoft YaHei UI',15,'bold')).pack(side='left',padx=22,pady=14)
        tk.Label(header,text='双站商品采集与发布管理系统  v1.0 开发验证版',fg='#64748b',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(side='left',padx=16)
        tk.Label(header,text='●  数据库已就绪  ·  实站采集待验证',fg='#1a8b65',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(side='right',padx=24)
        self.sidebar=tk.Frame(self,bg='#ffffff',width=184,highlightbackground='#e0e9f5',highlightthickness=1)
        self.sidebar.grid(row=1,column=0,sticky='ns');self.sidebar.grid_propagate(False)
        tk.Label(self.sidebar,text='功能导航',fg='#96a3b5',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(anchor='w',padx=20,pady=(25,12))
        style=ttk.Style(self)
        style.layout('Hidden.TNotebook.Tab', [])
        self.tabs=ttk.Notebook(self,style='Hidden.TNotebook');self.tabs.grid(row=1,column=1,sticky='nsew',padx=12,pady=12)
        self.nav_buttons=[]
        self.status=tk.StringVar(value='就绪 · 正式采集之前先验证两个网站的列表字段')
        self._build_overview();self._build_categories();self._build_full_scan();self._build_goods();self._build_projects();self._build_automation();self._build_capture();self._build_telegram();self._build_reports();self._build_settings();self._build_collect()
        self.tabs.bind('<<NotebookTabChanged>>',lambda e:self._refresh_nav())
        self.tabs.select(0);self._refresh_nav()
        footer=tk.Label(self,textvariable=self.status,anchor='w',bg='#ffffff',fg='#60718a',font=('Microsoft YaHei UI',10))
        footer.grid(row=2,column=0,columnspan=2,sticky='ew',padx=8,pady=5)
        self.refresh_all();self.protocol('WM_DELETE_WINDOW',self._exit)
        self.after(20000,self._poll_jobs)
        self.after(150,self._drain_progress)

    def _setup_theme(self):
        style=ttk.Style(self)
        try: style.theme_use('clam')
        except tk.TclError: pass
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f8fbff',foreground='#25364d')
        style.configure('TFrame',background='#f8fbff')
        style.configure('TLabel',background='#f8fbff',foreground='#25364d')
        style.configure('TLabelframe',background='#f8fbff')
        style.configure('TLabelframe.Label',background='#f8fbff',foreground='#1d4b89',font=('Microsoft YaHei UI',10,'bold'))
        style.configure('TButton',padding=(12,7),background='#e9f1ff',foreground='#1556bd')
        style.map('TButton',background=[('active','#cfe0ff')])
        style.configure('Treeview',background='#ffffff',fieldbackground='#ffffff',foreground='#1d3049',rowheight=31,font=('Microsoft YaHei UI',10))
        style.configure('Treeview.Heading',background='#eaf2ff',foreground='#23476c',font=('Microsoft YaHei UI',10,'bold'))
        style.map('Treeview',background=[('selected','#cfe3ff')],foreground=[('selected','#0c376b')])

    def _refresh_nav(self):
        current=self.tabs.index(self.tabs.select())
        for i,b in enumerate(self.nav_buttons):
            b.configure(bg='#1767ff' if i==current else '#ffffff',fg='#ffffff' if i==current else '#31435e')

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
        index=len(self.nav_buttons)
        names={'网站类目管理':'☷  网站类目管理','全站采集':'◎  全站采集','Telegram 发布':'➤  Telegram 发布','统计报表':'▥  统计报表','总览':'⌂  总览首页','商品数据库':'▤  商品数据库','项目与定价':'▣  项目管理',
               '网站采集':'⌕  单链接诊断','截图输出':'▧  截图模板',
               '全站与自动化':'◷  采集任务管理','系统与文件夹':'⚙  系统设置'}
        b=tk.Button(self.sidebar,text=names.get(label,label),font=('Microsoft YaHei UI',11),
                    bg='#ffffff',fg='#31435e',bd=0,anchor='w',padx=20,pady=12,
                    activebackground='#dceaff',command=lambda i=index:self.tabs.select(i),cursor='hand2')
        b.pack(fill='x',padx=10,pady=2)
        self.nav_buttons.append(b)
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
        ttk.Label(f,text='总览首页  ·  双站商品数据与任务状态',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=12)
        self.overview=tk.Text(f,height=16,font=('Microsoft YaHei UI',13),state='disabled',wrap='word',
                              bg='#ffffff',fg='#234365',relief='flat',padx=20,pady=18)
        self.overview.grid(row=1,column=0,sticky='nsew',pady=12)
        ttk.Label(f,text='主入口请使用「全站与自动化」：自动发现商品、定时更新库存、定时生成项目图片并通过 Telegram Bot 发布。网页适配仍需真实站点验证。',wraplength=900).grid(row=2,column=0,sticky='w')

    def _build_categories(self):
        f=self._frame('网站类目管理')
        ttk.Label(f,text='网站原始类目 · 先发现，再勾选采集',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=10)
        top=ttk.Frame(f);top.grid(row=2,column=0,sticky='ew',pady=6)
        self.category_source=tk.StringVar(value='FB1314')
        ttk.Combobox(top,textvariable=self.category_source,values=['FB1314','CEOACC'],state='readonly',width=14).pack(side='left',padx=4)
        ttk.Button(top,text='发现所选网站类目',command=lambda:self.run_manual('categories',self.category_source.get())).pack(side='left',padx=4)
        ttk.Button(top,text='刷新类目清单',command=self.refresh_categories).pack(side='left',padx=4)
        self.category_table=self._table_at(f,1,['ID','网站','原始类目','类目地址','监控状态'])
        self.category_table.column('原始类目',width=260)
        self.category_table.column('类目地址',width=440)
        actions=ttk.Frame(f);actions.grid(row=3,column=0,sticky='w',pady=8)
        for label,state in [('启用选中类目','enabled'),('暂停监控','paused'),('长期排除','excluded'),('待审核','review')]:
            ttk.Button(actions,text=label,command=lambda state=state:self.change_category_state(state)).pack(side='left',padx=4)
        ttk.Label(f,text='分类目录只存网站原始分类标识。未启用的分类不会进入周期扫描，也不会写入商品记录；只有完整扫描可提交数据库。',wraplength=990).grid(row=4,column=0,sticky='w',pady=10)
        self.category_source.trace_add('write',lambda *_:self.refresh_categories())

    def refresh_categories(self):
        if not hasattr(self,'category_table'):return
        self.category_table.delete(*self.category_table.get_children())
        for c in self.store.categories(self.category_source.get()):
            state={'review':'待审核','enabled':'持续监控','paused':'暂停','excluded':'长期排除'}.get(c['state'],c['state'])
            self.category_table.insert('','end',iid=str(c['id']),values=(c['id'],c['source'],c['title'],c['category_key'],state))

    def change_category_state(self,state):
        ids=self.category_table.selection()
        if not ids:return messagebox.showinfo('提示','先选择一条或多条网站类目')
        self.store.set_category_state(ids,state)
        self.refresh_categories();self.status.set(f'已修改 {len(ids)} 个类目的监控状态')

    def _build_full_scan(self):
        f=self._frame('全站采集')
        ttk.Label(f,text='全站采集中心',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=10)
        panel=ttk.LabelFrame(f,text='所选网站类目采集（先在网站类目管理中勾选）',padding=20)
        panel.grid(row=1,column=0,sticky='nsew',padx=12,pady=18)
        panel.columnconfigure(0,weight=1)
        ttk.Label(panel,text='全站建库与项目监控是两套独立任务。只会扫描已启用的网站原始类目；原始类目未启用前，不采集该类目商品。',wraplength=900).grid(row=0,column=0,sticky='w',pady=12)
        ttk.Button(panel,text='开始 FB1314 已选类目采集',command=lambda:self.run_manual('discover','FB1314')).grid(row=1,column=0,sticky='w',pady=8)
        ttk.Button(panel,text='开始 CEOACC 已选类目采集',command=lambda:self.run_manual('discover','CEOACC')).grid(row=2,column=0,sticky='w',pady=8)
        self._add_scan_progress_panel(panel,row=3)
        ttk.Label(panel,text='扫描未完成、无有效 USD/库存、网站限流等会记录异常；不能将零结果当作扫描成功。',wraplength=900).grid(row=4,column=0,sticky='w',pady=15)
        ttk.Label(panel,text='定期自动采集：前往「采集任务管理」，建立选定类目采集任务（每 N 小时），项目截图与发布分别设置。',wraplength=900).grid(row=5,column=0,sticky='w')

    def _build_goods(self):
        f=self._frame('商品数据库');top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew')
        self.source_var=tk.StringVar(value='全部');self.state_var=tk.StringVar(value='全部');self.search_var=tk.StringVar()
        ttk.Label(top,text='来源').pack(side='left');ttk.Combobox(top,textvariable=self.source_var,values=['全部','FB1314','CEOACC'],state='readonly',width=10).pack(side='left',padx=5)
        ttk.Label(top,text='状态').pack(side='left');ttk.Combobox(top,textvariable=self.state_var,values=['全部','review','active','paused','excluded'],state='readonly',width=11).pack(side='left',padx=5)
        ttk.Entry(top,textvariable=self.search_var,width=25).pack(side='left',padx=8)
        ttk.Button(top,text='筛选 / 刷新',command=self.refresh_goods).pack(side='left',padx=4)
        ttk.Button(top,text='导入 CSV',command=self.import_csv_file).pack(side='left',padx=4)
        self.goods=self._table(f,['ID','网站','商品ID','原始名称','自定义名称','原价 USD','售价 USD','库存','状态'],{'原始名称':220,'自定义名称':220,'商品ID':110})
        buttons=ttk.Frame(f);buttons.grid(row=2,column=0,sticky='w',pady=7)
        for text,status in [('启用采集','active'),('暂停采集','paused'),('永久排除','excluded'),('待审核','review')]:
            ttk.Button(buttons,text=text,command=lambda s=status:self.change_status(s)).pack(side='left',padx=5)
        ttk.Button(buttons,text='编辑展示名称和售价',command=self.edit_product).pack(side='left',padx=5)
        ttk.Button(buttons,text='查看库存历史',command=self.show_history).pack(side='left',padx=5)

    def _build_projects(self):
        f=self._frame('项目与定价');top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew')
        ttk.Button(top,text='新建项目',command=self.create_project).pack(side='left',padx=4)
        self.project_var=tk.StringVar();self.project_box=ttk.Combobox(top,textvariable=self.project_var,state='readonly',width=30)
        self.project_box.pack(side='left',padx=8);self.project_box.bind('<<ComboboxSelected>>',lambda e:self.refresh_projects())
        ttk.Button(top,text='将商品页所选商品加入本项目',command=self.assign_products).pack(side='left',padx=4)
        ttk.Button(top,text='编辑项目专属名称与售价',command=self.edit_project_product).pack(side='left',padx=4)
        self.project_table=self._table(f,['ID','网站','项目展示名称','原始商品名','原价 USD','项目售价 USD','库存'],{'项目展示名称':260,'原始商品名':240})

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
        ttk.Label(body,text='截图销量指标（可任意多选，每项目独立保存）：').grid(row=3,column=0,sticky='w',pady=8)
        options=ttk.Frame(body);options.grid(row=3,column=1,sticky='w')
        self.sales_vars={key:tk.BooleanVar() for key in ('24h','7d','30d')}
        for key,label in [('24h','24小时预估'),('7d','7天预估'),('30d','30天预估')]:
            ttk.Checkbutton(options,text=label,variable=self.sales_vars[key]).pack(side='left',padx=8)
        self.render_box.bind('<<ComboboxSelected>>',lambda e:self._load_sales_periods())
        ttk.Button(body,text='保存当前项目销量选项',command=self._save_sales_periods).grid(row=4,column=1,sticky='w',pady=8)
        ttk.Button(body,text='生成项目 PNG 报价图片',command=self.export_png).grid(row=5,column=1,sticky='w',pady=12)
        ttk.Label(body,text='图片渲染使用 Pillow；自动截图与 Telegram 发布任务请在「全站与自动化」配置。').grid(row=6,column=0,columnspan=2,sticky='w')

    def _build_automation(self):
        f=self._frame('全站与自动化')
        top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew',pady=5)
        ttk.Label(top,text='按已启用的原始网站类目读取商品，不读取被长期排除的类目；首次请先发现类目并选择。',wraplength=900).pack(anchor='w')
        btns=ttk.Frame(top);btns.pack(anchor='w',pady=6)
        ttk.Button(btns,text='立即扫描已选类目 FB1314',command=lambda:self.run_manual('discover','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='立即扫描已选类目 CEOACC',command=lambda:self.run_manual('discover','CEOACC')).pack(side='left',padx=3)
        ttk.Button(btns,text='刷新 FB1314 已选类目',command=lambda:self.run_manual('refresh','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='刷新 CEOACC 已选类目',command=lambda:self.run_manual('refresh','CEOACC')).pack(side='left',padx=3)
        form=ttk.LabelFrame(f,text='新增定时任务',padding=8);form.grid(row=1,column=0,sticky='ew',pady=6)
        self.job_kind=tk.StringVar(value=KIND_ZH['discover']);self.job_source=tk.StringVar(value='FB1314')
        self.job_interval=tk.StringVar(value='6');self.job_daily=tk.StringVar();self.job_target=tk.StringVar();self.job_caption=tk.StringVar(value='每日商品报价 · 库存价格以最新数据为准')
        self.job_project=tk.StringVar()
        ttk.Label(form,text='任务类型').grid(row=0,column=0,sticky='w')
        ttk.Combobox(form,textvariable=self.job_kind,values=list(KIND_ZH.values()),state='readonly',width=22).grid(row=0,column=1,padx=5)
        ttk.Label(form,text='网站').grid(row=0,column=2)
        ttk.Combobox(form,textvariable=self.job_source,values=['FB1314','CEOACC'],state='readonly',width=11).grid(row=0,column=3,padx=5)
        ttk.Label(form,text='循环间隔(小时)').grid(row=0,column=4)
        ttk.Spinbox(form,textvariable=self.job_interval,from_=1,to=720,increment=1,width=7).grid(row=0,column=5,padx=5)
        ttk.Label(form,text='固定每日时间（可选，格式 08:00,20:00；填入后优先于循环小时）').grid(row=5,column=0,columnspan=3,sticky='w')
        ttk.Entry(form,textvariable=self.job_daily,width=26).grid(row=5,column=3,columnspan=3,sticky='w')
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
        self._add_scan_progress_panel(f,row=5)
        f.rowconfigure(2,weight=1)
        self.job_table=self._table_at(f,2,['ID','任务类型','网站/项目','循环(小时)','目标','下次运行','最近错误'])
        ctl=ttk.Frame(f);ctl.grid(row=3,column=0,sticky='w',pady=4)
        ttk.Button(ctl,text='立即执行选中任务',command=self.run_selected_job).pack(side='left',padx=3)
        ttk.Button(ctl,text='删除选中任务',command=self.delete_selected_job).pack(side='left',padx=3)
        ttk.Button(ctl,text='刷新列表',command=self.refresh_jobs).pack(side='left',padx=3)
        ttk.Label(ctl,text='已选类目可设置每2小时、每6小时或任意整数小时循环执行。').pack(side='left',padx=12)

    def _add_scan_progress_panel(self,parent,row):
        # Unknown total pages: intentionally indeterminate, never show fictional percentages.
        panel=ttk.LabelFrame(parent,text='采集实时进度（未知总量时显示扫描状态，不虚报百分比）',padding=10)
        panel.grid(row=row,column=0,sticky='ew',pady=7)
        panel.columnconfigure(0,weight=1)
        if not hasattr(self,'progress_text'):
            self.progress_text=tk.StringVar(value='待命 · 尚未开始采集')
            self.progress_detail=tk.StringVar(value='扫描页面 0 · 识别商品 0 · 无效数据 0 · 失败页面 0')
        ttk.Label(panel,textvariable=self.progress_text).grid(row=0,column=0,sticky='w')
        ttk.Label(panel,textvariable=self.progress_detail).grid(row=1,column=0,sticky='w',pady=4)
        bar=ttk.Progressbar(panel,mode='indeterminate',length=490)
        bar.grid(row=2,column=0,sticky='ew',pady=5)
        if not hasattr(self,'progress_bars'):self.progress_bars=[]
        self.progress_bars.append(bar)
        ttk.Button(panel,text='停止当前扫描',command=self._cancel_scan).grid(row=3,column=0,sticky='w',pady=3)

    def _cancel_scan(self):
        if not self.active_job:
            self.status.set('当前没有运行中的采集任务')
            return
        self.stop_scan.set()
        self.progress_text.set('正在请求停止：当前网页操作结束后安全退出……')

    def _drain_progress(self):
        try:
            while True:
                update=self.progress_messages.get_nowait()
                visited=update.get('visited',0)
                listed=update.get('listed',0)
                incomplete=update.get('incomplete_cards',0)
                failed=update.get('failed',0)
                scroll=update.get('scroll_round',update.get('scroll_rounds',0))
                current=update.get('current_url','')
                phase=update.get('stage','扫描中')
                self.progress_text.set(f'{phase} · {current[:95]}')
                self.progress_detail.set(f'已访问页面 {visited} · 已识别商品 {listed} · 待核实字段 {incomplete} · 失败页面 {failed} · 本页滚动 {scroll}')
        except queue.Empty:
            pass
        if self.winfo_exists():self.after(150,self._drain_progress)

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
            self.job_table.insert('','end',iid=str(j['id']),values=(j['id'],KIND_ZH.get(j['kind'],j['kind']),scope,('每天 '+j['daily_times'] if j['daily_times'] else str(round(j['interval_minutes']/60,2))),j['target'],when,j['last_error'][:80]))

    def configure_bot(self):
        token=simpledialog.askstring('Telegram Bot Token','请输入 BotFather 提供的 Bot Token（将以 Windows 用户加密方式保存）：',show='*',parent=self)
        if not token:return
        try:
            self.settings['tg_token_encrypted']=protect_token(token.strip());self._save_settings()
            messagebox.showinfo('已保存','Bot Token 已使用 Windows DPAPI 加密保存。')
        except Exception as exc:messagebox.showerror('保存失败',str(exc))

    def create_job(self):
        try:
            kind=ZH_KIND[self.job_kind.get()];source=self.job_source.get() if kind not in ('capture','publish') else ''
            pid=self._project_id(self.job_project.get()) if kind in ('capture','publish') else None
            if kind in ('capture','publish') and not pid:raise ValueError('截图/发布任务需要选择一个项目')
            if kind=='publish' and not self.job_target.get().strip():raise ValueError('发布任务需要目标频道/群组')
            hours=float(self.job_interval.get())
            if hours < 1 or hours > 720:raise ValueError('循环间隔请填写 1 至 720 小时')
            self.store.add_job(KIND_ZH[kind]+' '+(source or str(pid)),kind,round(hours*60),source,pid,
              self.job_target.get().strip() if kind=='publish' else '',self.job_caption.get() if kind=='publish' else '',self.job_daily.get())
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
        self.active_job=True;self.stop_scan.clear();self.status.set('正在执行 '+KIND_ZH.get(job['kind'],job['kind'])+'...')
        if job['kind'] in ('categories','discover','refresh'):
            self.progress_text.set('准备连接网站 · 正在启动浏览器……')
            self.progress_detail.set('已访问页面 0 · 已识别商品 0 · 待核实字段 0 · 失败页面 0')
            for bar in self.progress_bars:bar.start(12)
        settings=dict(self.settings);db_path=str(self.store.path)
        def work():
            error=''
            try:result=execute(job,db_path,settings,progress=self.progress_messages.put,stop=self.stop_scan)
            except Exception as exc:error=str(exc);result='任务失败：'+error
            self.after(0,lambda:self._finish_automation(job,result,error))
        threading.Thread(target=work,daemon=True).start()

    def _finish_automation(self,job,result,error):
        self.active_job=False
        for bar in self.progress_bars:bar.stop()
        if job['kind'] in ('categories','discover','refresh'):
            self.progress_text.set('采集已结束' if not self.stop_scan.is_set() else '用户已请求停止，任务结束')
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

    def _build_telegram(self):
        f=self._frame('Telegram 发布')
        ttk.Label(f,text='Telegram 发布中心',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=10)
        body=ttk.LabelFrame(f,text='Bot 连接与项目发布',padding=18)
        body.grid(row=1,column=0,sticky='nsew',padx=12,pady=16)
        ttk.Label(body,text='当前版本发布方式：Telegram Bot API；无需使用个人账号密码。',wraplength=900).pack(anchor='w',pady=10)
        ttk.Label(body,text='发布内容读取项目中的自定义名称、项目售价和最新库存；生成白色 PNG 后上传到已授权频道。',wraplength=900).pack(anchor='w',pady=8)
        ttk.Button(body,text='配置 Telegram Bot Token',command=self.configure_bot).pack(anchor='w',pady=10)
        ttk.Button(body,text='前往采集任务管理 · 创建定时发布任务',command=lambda:self.tabs.select(self._page_index('全站与自动化'))).pack(anchor='w',pady=10)
        ttk.Label(body,text='发布前请将机器人加入目标频道/群组并授予发消息权限；先测试私有测试频道，不要立即大规模发布。',wraplength=900).pack(anchor='w',pady=10)

    def _page_index(self,label):
        for index in range(self.tabs.index('end')):
            if self.tabs.tab(index,'text')==label:return index
        return 0

    def _build_reports(self):
        f=self._frame('统计报表')
        ttk.Label(f,text='库存变化与估算销量',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=10)
        self.report_text=tk.Text(f,height=22,font=('Microsoft YaHei UI',12),state='disabled',wrap='word',
                                 bg='#ffffff',fg='#233c59',relief='flat',padx=20,pady=16)
        self.report_text.grid(row=1,column=0,sticky='nsew',pady=12)
        ttk.Label(f,text='说明：估算销量 = 两次有效库存快照间观察到的减少量，真实销量可能受补货和人工库存调整影响。',wraplength=900).grid(row=2,column=0,sticky='w')

    def refresh_reports(self):
        from datetime import timedelta
        since=(datetime.now().astimezone()-timedelta(hours=24)).isoformat(timespec='seconds')
        records=self.store.conn.execute("""SELECT p.source,COUNT(*) events,
            SUM(CASE WHEN s.stock_delta<0 THEN -s.stock_delta ELSE 0 END) decline,
            SUM(CASE WHEN s.stock_delta>0 THEN s.stock_delta ELSE 0 END) increase
            FROM snapshots s JOIN products p ON p.id=s.product_id
            WHERE s.captured_at>=? GROUP BY p.source""",(since,)).fetchall()
        lines=['最近 24 小时的有效库存变化','—'*36]
        if not records:lines.append('暂无有效快照。先执行全站建库和项目监控，再查看变化。')
        for r in records:
            lines.append(f"{r['source']}  快照 {r['events']} 次  |  观察到减少 {r['decline'] or 0}  |  观察到增加 {r['increase'] or 0}")
        lines += ['','数据只来自成功写入数据库的历史快照。','项目发布根据所选项目及截图模板生成，发布与全站扫描互不绑定。']
        self.report_text.configure(state='normal');self.report_text.delete('1.0','end');self.report_text.insert('1.0','\n'.join(lines));self.report_text.configure(state='disabled')

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
        self.refresh_goods();self.refresh_projects();self.refresh_categories();self.refresh_overview();self.refresh_jobs();self.refresh_reports()

    def refresh_overview(self):
        stats=self.store.stats();lines=['双站商品监控概览','='*42]
        for name,d in stats.items():lines.append(f'{name:10}  商品数：{d["count"]:>5}   待审核新品：{d["review"]:>5}')
        lines.extend(['','数据库位置：'+str(self.store.path),'截图目录：'+self.settings['screens_dir'],
                      '备份目录：'+self.settings['backup_dir'],'','版本：v1.0 开发验证版；已加入原始类目筛选和原价隔离，真实网站覆盖率与发布仍需验证。'])
        self.overview.configure(state='normal');self.overview.delete('1.0','end');self.overview.insert('1.0','\n'.join(lines));self.overview.configure(state='disabled')

    def refresh_goods(self):
        self.goods.delete(*self.goods.get_children())
        source=self.source_var.get();state=self.state_var.get()
        for p in self.store.products('' if source=='全部' else source,'' if state=='全部' else state,self.search_var.get().strip()):
            self.goods.insert('', 'end',iid=str(p['id']),values=(p['id'],p['source'],p['external_id'],p['name'],p['display_name'] or '（跟随原始名称）',p['raw_usd'],p['display_usd'] or '待定价',p['stock'] if p['stock'] is not None else '未知',p['status']))

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
        if hasattr(self,'sales_vars'):self._load_sales_periods()
        self.project_table.delete(*self.project_table.get_children())
        pid=self._project_id()
        if pid:
            for r in self.store.project_products(pid):
                self.project_table.insert('','end',iid=str(r['id']),values=(r['id'],r['source'],r['effective_name'],r['name'],r['raw_usd'],r['effective_usd'],r['stock'] if r['stock'] is not None else '未知'))

    def create_project(self):
        name=simpledialog.askstring('新建项目','输入项目名称：',parent=self)
        if not name:return
        try:self.store.add_project(name);self.refresh_projects();self.refresh_jobs()
        except sqlite3.IntegrityError:messagebox.showerror('重复','已存在同名项目')

    def assign_products(self):
        pid=self._project_id();ids=self.goods.selection()
        if not pid or not ids:return messagebox.showinfo('提示','先选择项目，再前往商品数据库选中商品')
        self.store.project_assign(pid,ids);self.refresh_projects();self.status.set(f'已添加 {len(ids)} 件商品到项目')

    def _edit_dialog(self,title,raw_name,raw_price,default_name,default_price,on_save):
        win=tk.Toplevel(self);win.title(title);win.geometry('570x350');win.configure(bg='#f8fbff')
        win.transient(self);win.grab_set()
        frame=ttk.Frame(win,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='原始名称（网站自动更新）：'+raw_name,wraplength=510).pack(anchor='w',pady=(2,8))
        ttk.Label(frame,text='原始价格 USD（只读）：'+str(raw_price)).pack(anchor='w',pady=(0,14))
        ttk.Label(frame,text='自定义展示名称（留空跟随原始名称）').pack(anchor='w')
        name=tk.StringVar(value=default_name or '')
        ttk.Entry(frame,textvariable=name,width=60).pack(fill='x',pady=(4,13))
        ttk.Label(frame,text='自定义售价 USD（留空则无法对外截图/发布，绝不回退原价）').pack(anchor='w')
        price=tk.StringVar(value=default_price or '')
        ttk.Entry(frame,textvariable=price,width=40).pack(fill='x',pady=(4,12))
        ttk.Label(frame,text='网站采集始终以来源网站 + 商品ID + 规格匹配，不受改名、改价影响。',wraplength=510).pack(anchor='w')
        def commit():
            try:
                on_save(name.get(),price.get());self.refresh_all();win.destroy()
            except Exception as e:messagebox.showerror('保存失败',str(e),parent=win)
        ttk.Button(frame,text='保存展示信息',command=commit).pack(anchor='e',pady=14)
        win.wait_window()

    def edit_product(self):
        ids=self.goods.selection()
        if len(ids)!=1:return messagebox.showinfo('提示','请先在商品数据库中选中一件商品')
        item=self.store.conn.execute('SELECT * FROM products WHERE id=?',(int(ids[0]),)).fetchone()
        if not item:return
        self._edit_dialog('全局自定义展示信息',item['name'],item['raw_usd'],item['display_name'],item['display_usd'],
            lambda name,price:self.store.set_display(item['id'],name,price))

    def edit_project_product(self):
        pid=self._project_id();ids=self.project_table.selection()
        if not pid or len(ids)!=1:return messagebox.showinfo('提示','请在项目中选择一件商品')
        row=next((r for r in self.store.project_products(pid) if str(r['id'])==ids[0]),None)
        if not row:return
        self._edit_dialog('项目专属展示信息',row['name'],row['raw_usd'],row['custom_name'],row['custom_usd'],
            lambda name,price:self.store.set_project_display(pid,row['id'],name,price))

    def set_price(self):
        pid=self._project_id();ids=self.project_table.selection()
        if not pid or not ids:return messagebox.showinfo('提示','请选择项目中的商品')
        price=simpledialog.askstring('项目独立定价','请输入 USD 销售价，留空则标记待定价，禁止对外截图：',parent=self)
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

    def _selected_sales_periods(self):
        return tuple(k for k,v in self.sales_vars.items() if v.get())

    def _load_sales_periods(self):
        pid=self._project_id(self.render_project.get())
        periods=self.store.get_project_periods(pid) if pid else ()
        for k,v in self.sales_vars.items():v.set(k in periods)

    def _save_sales_periods(self):
        pid=self._project_id(self.render_project.get())
        if not pid:return messagebox.showinfo('提示','先选择项目')
        self.store.set_project_periods(pid,self._selected_sales_periods())
        self.status.set('当前项目的销量显示字段已保存')

    def export_png(self):
        pid=self._project_id(self.render_project.get())
        if not pid:return messagebox.showinfo('提示','请先创建项目')
        records=self.store.project_products(pid)
        if not records:return messagebox.showinfo('提示','项目没有商品')
        try:
            from image_render import render_project
            proj=self.store.conn.execute('SELECT name FROM projects WHERE id=?',(pid,)).fetchone()
            periods=self._selected_sales_periods()
            self.store.set_project_periods(pid,periods)
            paths=render_project(records,proj['name'],self.settings['screens_dir'],
                                 title=self.render_title.get() or '商品报价',footer=self.render_footer.get(),
                                 sales_periods=periods,sales_by_product=self.store.project_sales(pid))
            self.settings['render_title']=self.render_title.get();self.settings['render_footer']=self.render_footer.get()
            self._save_settings();self.status.set('已生成：'+str(paths[0]))
            messagebox.showinfo('报价图片已生成',f'共 {len(paths)} 张：\n{paths[0]}')
        except Exception as e:messagebox.showerror('生成失败',str(e))

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
