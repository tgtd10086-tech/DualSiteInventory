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

APP='黑盒铺子 · 库存监控与自动发布系统 v2.2 候选版'
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
        tk.Label(header,text='库存监控与自动发布系统  v2.2 候选版',fg='#64748b',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(side='left',padx=16)
        tk.Label(header,text='●  数据库已就绪  ·  实站采集待验证',fg='#1a8b65',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(side='right',padx=24)
        self.sidebar=tk.Frame(self,bg='#ffffff',width=184,highlightbackground='#e0e9f5',highlightthickness=1)
        self.sidebar.grid(row=1,column=0,sticky='ns');self.sidebar.grid_propagate(False)
        tk.Label(self.sidebar,text='功能导航',fg='#96a3b5',bg='#ffffff',font=('Microsoft YaHei UI',10)).pack(anchor='w',padx=20,pady=(25,12))
        style=ttk.Style(self)
        style.layout('Hidden.TNotebook.Tab', [])
        self.tabs=ttk.Notebook(self,style='Hidden.TNotebook');self.tabs.grid(row=1,column=1,sticky='nsew',padx=12,pady=12)
        self.nav_buttons=[]
        self.status=tk.StringVar(value='就绪 · 正式采集之前先验证两个网站的列表字段')
        self._build_overview();self._build_categories();self._build_full_scan();self._build_goods();self._build_projects();self._build_automation();self._build_capture();self._build_reports();self._build_settings();self._build_collect();self._build_logs()
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
               '全站与自动化':'◷  采集任务管理','系统与文件夹':'⚙  系统设置','截图输出':'▧  截图模板管理','采集日志':'≡  采集日志'}
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
        sy=ttk.Scrollbar(box,orient='vertical',command=t.yview);sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(box,orient='horizontal',command=t.xview);sx.grid(row=1,column=0,sticky='ew')
        t.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
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
        ttk.Label(f,text='网站原始类目 · 发现后分别进入待选择、正在采集、已暂停、已排除区域',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=10)
        top=ttk.Frame(f);top.grid(row=2,column=0,sticky='ew',pady=6)
        self.category_source=tk.StringVar(value='FB1314')
        ttk.Combobox(top,textvariable=self.category_source,values=['FB1314','CEOACC'],state='readonly',width=14).pack(side='left',padx=4)
        ttk.Button(top,text='发现所选网站类目',command=lambda:self.run_manual('categories',self.category_source.get())).pack(side='left',padx=4)
        ttk.Button(top,text='刷新类目清单',command=self.refresh_categories).pack(side='left',padx=4)
        self.category_tabs=ttk.Notebook(f);self.category_tabs.grid(row=1,column=0,sticky='nsew',pady=6)
        self.category_tables={}
        for state,label in [('review','待选择'),('enabled','正在采集'),('paused','已暂停'),('excluded','已排除')]:
            page=ttk.Frame(self.category_tabs);page.rowconfigure(0,weight=1);page.columnconfigure(0,weight=1)
            self.category_tabs.add(page,text=label)
            self.category_tables[state]=self._table_at(page,0,['ID','网站','原始类目','类目地址','状态'])
            self.category_tables[state].configure(selectmode='extended')
            self.category_tables[state].column('原始类目',width=260);self.category_tables[state].column('类目地址',width=440)
        self.category_table=self.category_tables['review']
        self.category_tabs.bind('<<NotebookTabChanged>>',self._category_tab_changed)
        actions=ttk.Frame(f);actions.grid(row=3,column=0,sticky='w',pady=8)
        for label,state in [('移入正在采集','enabled'),('暂停监控','paused'),('长期排除','excluded'),('恢复待选择','review')]:
            ttk.Button(actions,text=label,command=lambda state=state:self.change_category_state(state)).pack(side='left',padx=4)
        ttk.Label(f,text='类目状态分区独立展示。排除类目不进入正式商品数据库；暂停类目保留历史但不继续刷新。',wraplength=990).grid(row=4,column=0,sticky='w',pady=10)
        self.category_source.trace_add('write',lambda *_:self.refresh_categories())

    def _category_tab_changed(self,event=None):
        if hasattr(self,'category_tabs'):
            index=self.category_tabs.index(self.category_tabs.select())
            state=['review','enabled','paused','excluded'][index]
            self.category_table=self.category_tables[state]

    def refresh_categories(self):
        if not hasattr(self,'category_tables'):return
        for table in self.category_tables.values():table.delete(*table.get_children())
        for c in self.store.categories(self.category_source.get()):
            state=c['state'];table=self.category_tables.get(state)
            if table:table.insert('','end',iid=str(c['id']),values=(c['id'],c['source'],c['title'],c['category_key'],{'review':'待选择','enabled':'正在采集','paused':'已暂停','excluded':'已排除'}.get(state,state)))
        self._category_tab_changed()

    def change_category_state(self,state):
        ids=self.category_table.selection()
        if not ids:return messagebox.showinfo('提示','先在当前类目分区选择一条或多条网站类目')
        self.store.set_category_state(ids,state)
        self.refresh_categories();self.status.set(f'已将 {len(ids)} 个类目移动到对应区域')

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
        self.source_var=tk.StringVar(value='全部');self.state_var=tk.StringVar(value='全部');self.search_var=tk.StringVar();self.membership_var=tk.StringVar(value='待归类');self.sort_var=tk.StringVar(value='24h销量从高到低');self.type_var=tk.StringVar(value='全部')
        ttk.Label(top,text='来源').pack(side='left');ttk.Combobox(top,textvariable=self.source_var,values=['全部','FB1314','CEOACC'],state='readonly',width=10).pack(side='left',padx=5)
        ttk.Label(top,text='归类状态').pack(side='left');ttk.Combobox(top,textvariable=self.membership_var,values=['全部商品','待归类','已归类','已排除'],state='readonly',width=10).pack(side='left',padx=5)
        ttk.Label(top,text='商品类型').pack(side='left');ttk.Combobox(top,textvariable=self.type_var,values=['全部','Facebook','Instagram','邮箱','其他'],state='readonly',width=10).pack(side='left',padx=5)
        ttk.Entry(top,textvariable=self.search_var,width=22).pack(side='left',padx=8)
        ttk.Button(top,text='筛选 / 刷新',command=self.refresh_goods).pack(side='left',padx=4)
        sortbar=ttk.Frame(top);sortbar.pack(side='left',padx=5)
        ttk.Label(sortbar,text='排序').pack(side='left')
        ttk.Combobox(sortbar,textvariable=self.sort_var,values=['最近更新','名称升序','名称降序','原价从低到高','原价从高到低','库存从低到高','库存从高到低','商品类型','24h销量从高到低','7天销量从高到低','30天销量从高到低'],state='readonly',width=22).pack(side='left',padx=6)
        ttk.Button(sortbar,text='应用排序',command=self.refresh_goods).pack(side='left')
        ttk.Button(top,text='导入 CSV',command=self.import_csv_file).pack(side='left',padx=4)
        self.goods=self._table(f,['ID','网站','商品ID','商品类型','原始名称','展示名称','原价 USD','售价 USD','库存','24h销量','7天销量','30天销量','所属项目','归类状态'],{'原始名称':190,'展示名称':190,'商品ID':105,'所属项目':180})
        buttons=ttk.Frame(f);buttons.grid(row=2,column=0,sticky='w',pady=7)
        for text,status in [('启用监控','active'),('暂停监控','paused'),('排除商品','excluded'),('恢复待归类','review')]:
            ttk.Button(buttons,text=text,command=lambda s=status:self.change_status(s)).pack(side='left',padx=3)
        self.goods_target_project=tk.StringVar()
        self.goods_project_box=ttk.Combobox(buttons,textvariable=self.goods_target_project,state='readonly',width=22)
        self.goods_project_box.pack(side='left',padx=3)
        ttk.Button(buttons,text='批量归入所选项目',command=self.assign_products).pack(side='left',padx=3)
        ttk.Button(buttons,text='批量改名',command=self.bulk_rename_products).pack(side='left',padx=3)
        ttk.Button(buttons,text='批量改价',command=self.bulk_edit_products).pack(side='left',padx=3)
        ttk.Button(buttons,text='编辑名称/售价',command=self.edit_product).pack(side='left',padx=3)
        ttk.Button(buttons,text='库存历史',command=self.show_history).pack(side='left',padx=3)

    def _build_projects(self):
        f=self._frame('项目与定价');top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew')
        ttk.Button(top,text='新建项目',command=self.create_project).pack(side='left',padx=4)
        self.project_var=tk.StringVar();self.project_box=ttk.Combobox(top,textvariable=self.project_var,state='readonly',width=30)
        self.project_box.pack(side='left',padx=8);self.project_box.bind('<<ComboboxSelected>>',lambda e:self.refresh_projects())
        ttk.Button(top,text='将商品页所选商品加入本项目',command=self.assign_products_to_current_project).pack(side='left',padx=4)
        ttk.Button(top,text='编辑项目专属名称与售价',command=self.edit_project_product).pack(side='left',padx=4)
        ttk.Button(top,text='项目批量改价',command=self.set_price).pack(side='left',padx=4)
        ttk.Button(top,text='从项目移除',command=self.remove_project_products).pack(side='left',padx=4)
        ttk.Button(top,text='截图显示/隐藏',command=self.toggle_project_capture).pack(side='left',padx=4)
        ttk.Button(top,text='缺货商品显示/隐藏',command=self.toggle_project_oos).pack(side='left',padx=4)
        ttk.Button(top,text='上移',command=lambda:self.move_project_product(-1)).pack(side='left',padx=2)
        ttk.Button(top,text='下移',command=lambda:self.move_project_product(1)).pack(side='left',padx=2)
        self.project_sort_var=tk.StringVar(value='手动固定顺序')
        ttk.Combobox(top,textvariable=self.project_sort_var,values=['手动固定顺序','本日销量从高到低','本周销量从高到低','本月销量从高到低','价格从低到高','价格从高到低','库存从低到高','库存从高到低'],state='readonly',width=20).pack(side='left',padx=5)
        ttk.Button(top,text='应用项目排序',command=self.apply_project_sort).pack(side='left',padx=3)
        self.project_table=self._table(f,['ID','网站','项目展示名称','原始商品名','原价 USD','项目售价 USD','库存','截图状态','固定序号'],{'项目展示名称':230,'原始商品名':210})

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
        f=self._frame('截图输出');f.rowconfigure(1,weight=1)
        body=ttk.LabelFrame(f,text='截图模板内容',padding=12);body.grid(row=1,column=0,sticky='ew',pady=8)
        ttk.Label(body,text='选择项目：').grid(row=0,column=0,sticky='w')
        self.render_project=tk.StringVar();self.render_box=ttk.Combobox(body,textvariable=self.render_project,state='readonly',width=35)
        self.render_box.grid(row=0,column=1,sticky='w',padx=10)
        ttk.Label(body,text='截图标题：').grid(row=1,column=0,sticky='w',pady=6)
        self.render_title=tk.StringVar(value=self.settings['render_title']);ttk.Entry(body,textvariable=self.render_title,width=55).grid(row=1,column=1,sticky='w')
        ttk.Label(body,text='底部文案：').grid(row=2,column=0,sticky='w',pady=6)
        self.render_footer=tk.StringVar(value=self.settings['render_footer']);ttk.Entry(body,textvariable=self.render_footer,width=55).grid(row=2,column=1,sticky='w')
        ttk.Label(body,text='截图销量指标（只能选择一项）：').grid(row=3,column=0,sticky='w',pady=6)
        options=ttk.Frame(body);options.grid(row=3,column=1,sticky='w')
        self.sales_period_var=tk.StringVar(value='24h')
        for key,label in [('24h','本日销量（24小时）'),('7d','本周销量（7天）'),('30d','本月销量（30天）')]:
            ttk.Radiobutton(options,text=label,variable=self.sales_period_var,value=key).pack(side='left',padx=8)
        self.render_box.bind('<<ComboboxSelected>>',lambda e:self._load_sales_periods())
        ttk.Button(body,text='保存当前项目截图模板',command=self._save_sales_periods).grid(row=4,column=1,sticky='w',pady=7)
        ttk.Button(body,text='生成项目 PNG 预览',command=self.export_png).grid(row=5,column=1,sticky='w',pady=7)

        schedule=ttk.LabelFrame(f,text='模板定时截图与 Telegram 发布（与网站采集任务完全分开）',padding=12)
        schedule.grid(row=2,column=0,sticky='ew',pady=8)
        self.tpl_job_kind=tk.StringVar(value='Telegram 定时发布')
        self.tpl_job_interval=tk.StringVar(value='24')
        self.tpl_job_start=tk.StringVar(value='')
        self.tpl_job_target=tk.StringVar(value='')
        self.tpl_job_caption=tk.StringVar(value='每日商品报价 · 库存价格以最新数据为准')
        ttk.Label(schedule,text='任务：').grid(row=0,column=0,sticky='w')
        ttk.Combobox(schedule,textvariable=self.tpl_job_kind,values=['定时生成截图','Telegram 定时发布'],state='readonly',width=18).grid(row=0,column=1,padx=5)
        ttk.Label(schedule,text='项目模板：').grid(row=0,column=2,sticky='w')
        self.tpl_project=ttk.Combobox(schedule,textvariable=self.render_project,state='readonly',width=25)
        self.tpl_project.grid(row=0,column=3,padx=5)
        ttk.Label(schedule,text='间隔（12–24小时）：').grid(row=1,column=0,sticky='w',pady=5)
        ttk.Spinbox(schedule,textvariable=self.tpl_job_interval,from_=12,to=24,width=7).grid(row=1,column=1,sticky='w')
        ttk.Label(schedule,text='首次开始时间（YYYY-MM-DD HH:MM，可留空）：').grid(row=1,column=2,sticky='w')
        ttk.Entry(schedule,textvariable=self.tpl_job_start,width=22).grid(row=1,column=3,sticky='w')
        ttk.Label(schedule,text='Telegram 群组/频道 ID：').grid(row=2,column=0,sticky='w')
        ttk.Entry(schedule,textvariable=self.tpl_job_target,width=24).grid(row=2,column=1,sticky='w',padx=5)
        ttk.Label(schedule,text='发布文案：').grid(row=2,column=2,sticky='w')
        ttk.Entry(schedule,textvariable=self.tpl_job_caption,width=34).grid(row=2,column=3,sticky='ew')
        ttk.Button(schedule,text='保存 Bot Token',command=self.configure_bot).grid(row=3,column=0,pady=7,sticky='w')
        ttk.Button(schedule,text='创建模板定时任务',command=self.create_capture_job).grid(row=3,column=1,pady=7,sticky='w')
        self.capture_job_table=self._table_at(f,3,['ID','任务类型','项目模板','循环(小时)','首次开始','下次运行','最近错误'])
        controls=ttk.Frame(f);controls.grid(row=4,column=0,sticky='w',pady=4)
        ttk.Button(controls,text='立即执行选中模板任务',command=lambda:self.run_selected_job_from(self.capture_job_table)).pack(side='left',padx=3)
        ttk.Button(controls,text='删除选中模板任务',command=lambda:self.delete_selected_job_from(self.capture_job_table)).pack(side='left',padx=3)
        ttk.Button(controls,text='刷新模板任务',command=self.refresh_jobs).pack(side='left',padx=3)
        ttk.Label(f,text='模板任务只负责生成截图及 Telegram 发布；网站扫描请前往「采集任务管理」。').grid(row=5,column=0,sticky='w')

    def _build_automation(self):
        f=self._frame('全站与自动化')
        top=ttk.Frame(f);top.grid(row=0,column=0,sticky='ew',pady=5)
        ttk.Label(top,text='这里只管理网站采集，不包含截图或 Telegram 发布。按已启用的网站原始类目扫描。',wraplength=900).pack(anchor='w')
        btns=ttk.Frame(top);btns.pack(anchor='w',pady=6)
        ttk.Button(btns,text='立即扫描已选类目 FB1314',command=lambda:self.run_manual('discover','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='立即扫描已选类目 CEOACC',command=lambda:self.run_manual('discover','CEOACC')).pack(side='left',padx=3)
        ttk.Button(btns,text='刷新 FB1314 已选类目',command=lambda:self.run_manual('refresh','FB1314')).pack(side='left',padx=3)
        ttk.Button(btns,text='刷新 CEOACC 已选类目',command=lambda:self.run_manual('refresh','CEOACC')).pack(side='left',padx=3)
        form=ttk.LabelFrame(f,text='新增循环采集任务',padding=8);form.grid(row=1,column=0,sticky='ew',pady=6)
        self.job_kind=tk.StringVar(value=KIND_ZH['discover']);self.job_source=tk.StringVar(value='FB1314')
        self.job_interval=tk.StringVar(value='6');self.job_start=tk.StringVar(value='')
        ttk.Label(form,text='任务类型').grid(row=0,column=0,sticky='w')
        ttk.Combobox(form,textvariable=self.job_kind,values=[KIND_ZH[k] for k in ('categories','discover','refresh')],state='readonly',width=22).grid(row=0,column=1,padx=5)
        ttk.Label(form,text='网站').grid(row=0,column=2)
        ttk.Combobox(form,textvariable=self.job_source,values=['FB1314','CEOACC'],state='readonly',width=11).grid(row=0,column=3,padx=5)
        ttk.Label(form,text='循环间隔（1–24小时）').grid(row=0,column=4)
        ttk.Spinbox(form,textvariable=self.job_interval,from_=1,to=24,width=7).grid(row=0,column=5,padx=5)
        ttk.Label(form,text='首次开始时间（YYYY-MM-DD HH:MM，可留空）').grid(row=1,column=0,columnspan=3,sticky='w',pady=6)
        ttk.Entry(form,textvariable=self.job_start,width=24).grid(row=1,column=3,sticky='w')
        ttk.Button(form,text='创建采集循环任务',command=self.create_job).grid(row=1,column=4,columnspan=2,sticky='w',padx=5)
        self._add_scan_progress_panel(f,row=5)
        f.rowconfigure(2,weight=1)
        self.job_table=self._table_at(f,2,['ID','任务类型','网站','循环(小时)','下次运行','最近错误'])
        ctl=ttk.Frame(f);ctl.grid(row=3,column=0,sticky='w',pady=4)
        ttk.Button(ctl,text='立即执行选中采集任务',command=lambda:self.run_selected_job_from(self.job_table)).pack(side='left',padx=3)
        ttk.Button(ctl,text='删除选中采集任务',command=lambda:self.delete_selected_job_from(self.job_table)).pack(side='left',padx=3)
        ttk.Button(ctl,text='刷新采集任务',command=self.refresh_jobs).pack(side='left',padx=3)

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
        import datetime as dt
        jobs=list(self.store.jobs())
        if hasattr(self,'job_table'):
            self.job_table.delete(*self.job_table.get_children())
            for j in jobs:
                if j['kind'] not in ('categories','discover','refresh'): continue
                when=dt.datetime.fromtimestamp(j['next_run']).strftime('%Y-%m-%d %H:%M')
                self.job_table.insert('','end',iid=str(j['id']),values=(j['id'],KIND_ZH.get(j['kind'],j['kind']),j['source'],
                    round(j['interval_minutes']/60,2),when,j['last_error'][:100]))
        if hasattr(self,'capture_job_table'):
            self.capture_job_table.delete(*self.capture_job_table.get_children())
            for j in jobs:
                if j['kind'] not in ('capture','publish'): continue
                when=dt.datetime.fromtimestamp(j['next_run']).strftime('%Y-%m-%d %H:%M')
                project=next((p['name'] for p in self.store.projects() if p['id']==j['project_id']),'项目已删除')
                start=j['start_at'] if 'start_at' in j.keys() else ''
                self.capture_job_table.insert('','end',iid=str(j['id']),values=(j['id'],KIND_ZH.get(j['kind'],j['kind']),project,
                    round(j['interval_minutes']/60,2),start,when,j['last_error'][:80]))
        if hasattr(self,'auto_project'):
            values=[f'{p["id"]} · {p["name"]}' for p in self.store.projects()]
            self.auto_project['values']=values
            if values and self.job_project.get() not in values:self.job_project.set(values[0])

    def configure_bot(self):
        token=simpledialog.askstring('Telegram Bot Token','请输入 BotFather 提供的 Bot Token（将以 Windows 用户加密方式保存）：',show='*',parent=self)
        if not token:return
        try:
            self.settings['tg_token_encrypted']=protect_token(token.strip());self._save_settings()
            messagebox.showinfo('已保存','Bot Token 已使用 Windows DPAPI 加密保存。')
        except Exception as exc:messagebox.showerror('保存失败',str(exc))

    def create_job(self):
        try:
            kind=ZH_KIND[self.job_kind.get()]
            if kind not in ('categories','discover','refresh'):
                raise ValueError('采集任务中心只允许创建网站采集任务')
            source=self.job_source.get()
            hours=int(self.job_interval.get())
            if not 1 <= hours <= 24:raise ValueError('采集循环周期必须为 1–24 小时')
            start_at=self.job_start.get().strip()
            self.store.add_job(KIND_ZH[kind]+' '+source,kind,hours*60,source,start_at=start_at)
            self.refresh_jobs();self.status.set('采集循环任务已添加')
        except Exception as exc:messagebox.showerror('创建采集任务失败',str(exc))

    def create_capture_job(self):
        try:
            kind='publish' if self.tpl_job_kind.get()=='Telegram 定时发布' else 'capture'
            pid=self._project_id(self.render_project.get())
            if not pid:raise ValueError('请先选择项目模板')
            hours=int(self.tpl_job_interval.get())
            if not 12 <= hours <= 24:raise ValueError('截图模板任务周期必须为 12–24 小时')
            target=self.tpl_job_target.get().strip() if kind=='publish' else ''
            if kind=='publish' and not target:raise ValueError('Telegram 发布任务需要群组/频道 ID')
            start_at=self.tpl_job_start.get().strip()
            caption=self.tpl_job_caption.get().strip() if kind=='publish' else ''
            self.store.add_job(KIND_ZH[kind]+' '+self.render_project.get(),kind,hours*60,'',pid,target,caption,start_at=start_at)
            self.refresh_jobs();self.status.set('截图模板定时任务已添加')
        except Exception as exc:messagebox.showerror('创建模板任务失败',str(exc))

    def run_selected_job_from(self,table):
        ids=table.selection()
        if not ids:return messagebox.showinfo('提示','请先选择一条任务')
        job=next((dict(j) for j in self.store.jobs() if str(j['id'])==ids[0]),None)
        if job:self._run_automation(job)

    def delete_selected_job_from(self,table):
        ids=table.selection()
        if not ids:return
        if messagebox.askyesno('确认','删除选中的定时任务？'):
            self.store.delete_job(ids[0]);self.refresh_jobs()

    def run_selected_job(self):
        return self.run_selected_job_from(self.job_table)

    def delete_selected_job(self):
        return self.delete_selected_job_from(self.job_table)

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
        if self.active_job:
            if job.get('claim_token'):
                self.store.release_job_claim(job['id'],job['claim_token'])
            return messagebox.showwarning('任务正在运行','一次仅允许运行一个采集或发布任务')
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
        self.refresh_all();self.refresh_jobs();self.refresh_logs();self.status.set(result)
        if not job.get('_scheduled'):
            if error:messagebox.showerror('自动任务失败',result)
            else:messagebox.showinfo('任务结果',result)

    def _poll_jobs(self):
        try:
            import time
            if not self.active_job:
                # Claim atomically in SQLite: a second desktop instance must not
                # launch the same scheduled collection/publish task concurrently.
                due=self.store.claim_due_job()
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
        ttk.Label(body,text='当前版本发布方式：Telegram Bot API；无需使用个人账号密码。每个项目可独立选择本日/本周/本月其中一种销量列，截图发布间隔为12–24小时。',wraplength=900).pack(anchor='w',pady=10)
        ttk.Label(body,text='发布内容读取项目中的自定义名称、项目售价和最新库存；生成白色 PNG 后上传到已授权频道。',wraplength=900).pack(anchor='w',pady=8)
        ttk.Button(body,text='配置 Telegram Bot Token',command=self.configure_bot).pack(anchor='w',pady=10)
        ttk.Button(body,text='前往采集任务管理 · 创建定时发布任务',command=lambda:self.tabs.select(self._page_index('全站与自动化'))).pack(anchor='w',pady=10)
        ttk.Label(body,text='发布前请将机器人加入目标频道/群组并授予发消息权限；先测试私有测试频道，不要立即大规模发布。',wraplength=900).pack(anchor='w',pady=10)

    def _page_index(self,label):
        for index in range(self.tabs.index('end')):
            if self.tabs.tab(index,'text')==label:return index
        return 0

    def _build_logs(self):
        f=self._frame('采集日志')
        ttk.Label(f,text='采集执行日志与诊断',font=('Microsoft YaHei UI',18,'bold')).grid(row=0,column=0,sticky='w',pady=8)
        bar=ttk.Frame(f);bar.grid(row=1,column=0,sticky='ew',pady=5)
        self.log_source=tk.StringVar(value='全部网站')
        ttk.Combobox(bar,textvariable=self.log_source,values=['全部网站','FB1314','CEOACC'],state='readonly',width=14).pack(side='left',padx=4)
        ttk.Button(bar,text='刷新日志',command=self.refresh_logs).pack(side='left',padx=4)
        ttk.Button(bar,text='打开日志目录',command=self.open_logs_folder).pack(side='left',padx=4)
        self.log_text=tk.Text(f,height=25,font=('Consolas',9),wrap='none',bg='#ffffff',fg='#233c59',relief='flat')
        self.log_text.grid(row=2,column=0,sticky='nsew',pady=6)
        f.rowconfigure(2,weight=1)
        ttk.Label(f,text='日志按任务、网站、时间记录；诊断 JSON 保存在 Documents\\DualSiteInventory\\Diagnostics 对应网站目录（无法写入时使用备用目录）。',wraplength=900).grid(row=3,column=0,sticky='w')

    def _logs_candidates(self):
        import tempfile
        return [Path(self.settings['data_dir']).parent/'Logs'/'collection',
                Path.home()/'Documents'/'DualSiteInventory'/'Logs'/'collection',
                Path(os.getenv('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'DualSiteInventory'/'Logs'/'collection',
                Path(tempfile.gettempdir())/'DualSiteInventory'/'Logs'/'collection']

    def _logs_root(self):
        for folder in self._logs_candidates():
            if folder.exists(): return folder
        return self._logs_candidates()[0]

    def refresh_logs(self):
        if not hasattr(self,'log_text'):return
        folders=[p for p in self._logs_candidates() if p.exists()]
        source=self.log_source.get() if hasattr(self,'log_source') else '全部网站'
        files=sorted({p for folder in folders for p in folder.glob('*.jsonl')})
        lines=[]
        for path in files:
            if source!='全部网站' and not path.name.startswith(source.lower()+'_'):continue
            try:
                rows=path.read_text(encoding='utf-8').splitlines()
                lines.extend(rows[-500:])
            except OSError as exc:
                lines.append(json.dumps({'level':'ERROR','file':str(path),'error':str(exc)},ensure_ascii=False))
        self.log_text.delete('1.0','end')
        self.log_text.insert('1.0','\n'.join(lines[-1500:]) if lines else '暂无采集日志。执行一次采集任务后，这里会记录任务开始、页面加载、商品识别、异常和任务结束。')

    def open_logs_folder(self):
        import os
        folder=self._logs_root()
        folder.mkdir(parents=True,exist_ok=True)
        try:os.startfile(str(folder))
        except Exception as exc:messagebox.showerror('打开日志目录失败',str(exc))

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
        self.refresh_goods();self.refresh_projects();self.refresh_categories();self.refresh_overview();self.refresh_jobs();self.refresh_reports();self.refresh_logs()

    def refresh_overview(self):
        stats=self.store.stats();lines=['双站商品监控概览','='*42]
        for name,d in stats.items():lines.append(f'{name:10}  商品数：{d["count"]:>5}   待审核新品：{d["review"]:>5}')
        lines.extend(['','数据库位置：'+str(self.store.path),'截图目录：'+self.settings['screens_dir'],
                      '备份目录：'+self.settings['backup_dir'],'','版本：v2.2 候选版；商品管理、项目关联、单一销量周期与简洁表格截图规则已更新，实站覆盖率及 TG 端到端仍需验收。'])
        self.overview.configure(state='normal');self.overview.delete('1.0','end');self.overview.insert('1.0','\n'.join(lines));self.overview.configure(state='disabled')

    def refresh_goods(self):
        self.goods.delete(*self.goods.get_children())
        source=self.source_var.get(); membership={'全部商品':'all','待归类':'pending','已归类':'assigned','已排除':'excluded'}.get(self.membership_var.get(),'all')
        sort_map={'最近更新':'updated_desc','名称升序':'name_asc','名称降序':'name_desc','原价从低到高':'price_asc','原价从高到低':'price_desc','库存从低到高':'stock_asc','库存从高到低':'stock_desc','商品类型':'type_asc','24h销量从高到低':'sales_24h','7天销量从高到低':'sales_7d','30天销量从高到低':'sales_30d'}
        ptype='' if self.type_var.get()=='全部' else self.type_var.get()
        rows=self.store.products_for_management('' if source=='全部' else source,membership,self.search_var.get().strip(),ptype,sort_map.get(self.sort_var.get(),'updated_desc'),limit=20000)
        for p in rows:
            state='已排除' if p['status']=='excluded' else ('已归类' if p['is_assigned'] else '待归类')
            self.goods.insert('','end',iid=str(p['id']),values=(p['id'],p['source'],p['external_id'],p['product_type'],p['name'],p['display_name'] or '（跟随原始名称）',p['raw_usd'],p['display_usd'] or '待定价',p['stock'] if p['stock'] is not None else '未知',p['sales24'],p['sales7'],p['sales30'],p['project_names'] or '—',state))

    def bulk_rename_products(self):
        ids=[int(x) for x in self.goods.selection()]
        if not ids:return messagebox.showinfo('提示','请先勾选一个或多个商品')
        prefix=simpledialog.askstring('批量改名','输入需要添加到商品名称前面的文字（可留空）：',parent=self)
        if prefix is None:return
        suffix=simpledialog.askstring('批量改名','输入需要添加到商品名称后面的文字（可留空）：',parent=self)
        if suffix is None:return
        self.store.bulk_set_display(ids,name_prefix=prefix,name_suffix=suffix,price_mode='keep')
        self.refresh_all();self.status.set(f'已批量更新 {len(ids)} 件商品的展示名称')

    def bulk_edit_products(self):
        ids=[int(x) for x in self.goods.selection()]
        if not ids:return messagebox.showinfo('提示','请先勾选一个或多个商品')
        mode=simpledialog.askstring('批量改价','输入固定 USD 售价；输入 +2 表示在已有自定义售价上加 2；输入 +10% 表示按已有自定义售价上调 10%。留空仅保留价格。',parent=self)
        if mode is None:return
        try:
            if not mode.strip():return
            if mode.startswith('+') and mode.endswith('%'):
                n=float(mode[1:-1]); self.store.bulk_set_display(ids,price_mode='percent',price_value=n)
            elif mode.startswith('+'):
                n=float(mode[1:]); self.store.bulk_set_display(ids,price_mode='add',price_value=n)
            else:self.store.bulk_set_display(ids,price=mode,price_mode='fixed')
            self.refresh_all();self.status.set(f'已批量更新 {len(ids)} 件商品的全局展示售价')
        except Exception as e:messagebox.showerror('批量改价失败',str(e))

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
        if hasattr(self,'goods_project_box'):
            self.goods_project_box['values']=values
            if values and self.goods_target_project.get() not in values:self.goods_target_project.set(values[0])
        if values and self.project_var.get() not in values:self.project_var.set(values[0])
        if values and self.render_project.get() not in values:self.render_project.set(values[0])
        if hasattr(self,'sales_period_var'):self._load_sales_periods()
        if hasattr(self,'project_sort_var') and values:
            selected=next((p for p in projects if f'{p["id"]} · {p["name"]}'==self.project_var.get()),projects[0])
            sort_labels={'manual':'手动固定顺序','sales_24h':'本日销量从高到低','sales_7d':'本周销量从高到低','sales_30d':'本月销量从高到低','price_asc':'价格从低到高','price_desc':'价格从高到低','stock_asc':'库存从低到高','stock_desc':'库存从高到低'}
            self.project_sort_var.set(sort_labels.get(selected['sort_mode'],'手动固定顺序'))
        self.project_table.delete(*self.project_table.get_children())
        pid=self._project_id()
        if pid:
            for r in self.store.project_products(pid):
                self.project_table.insert('','end',iid=str(r['id']),values=(r['id'],r['source'],r['effective_name'],r['name'],r['raw_usd'],r['effective_usd'],r['stock'] if r['stock'] is not None else '未知','显示' if r['include_in_capture'] else '隐藏',r['sort_order']))

    def create_project(self):
        name=simpledialog.askstring('新建项目','输入项目名称：',parent=self)
        if not name:return
        try:
            self.store.add_project(name)
            self.refresh_projects();self.refresh_jobs()
            created=next((p for p in self.store.projects() if p['name']==name.strip()),None)
            if created:
                self.project_var.set(f"{created['id']} · {created['name']}")
                self.refresh_projects()
                self.open_project_product_picker(created['id'], created['name'])
        except sqlite3.IntegrityError:messagebox.showerror('重复','已存在同名项目')

    def open_project_product_picker(self, project_id, project_name):
        """Create-project flow: select products with explicit checkbox column."""
        win=tk.Toplevel(self);win.title(f'选择商品 - {project_name}');win.geometry('1000x680');win.transient(self)
        win.grab_set()
        selected=set()
        search_var=tk.StringVar();source_var=tk.StringVar(value='全部网站')
        header=ttk.Frame(win,padding=12);header.pack(fill='x')
        ttk.Label(header,text=f'项目：{project_name}  |  勾选需要加入的商品，可多选').pack(side='left')
        controls=ttk.Frame(win,padding=(12,0,12,8));controls.pack(fill='x')
        ttk.Label(controls,text='搜索').pack(side='left')
        search=ttk.Entry(controls,textvariable=search_var,width=28);search.pack(side='left',padx=6)
        ttk.Label(controls,text='网站').pack(side='left',padx=(12,3))
        ttk.Combobox(controls,textvariable=source_var,values=['全部网站','FB1314','CEOACC'],state='readonly',width=12).pack(side='left')
        ttk.Label(controls,text='点击第一列勾选/取消').pack(side='right')
        table_frame=ttk.Frame(win,padding=(12,0,12,8));table_frame.pack(fill='both',expand=True)
        cols=('checked','source','name','type','price','stock','projects')
        tree=ttk.Treeview(table_frame,columns=cols,show='headings',selectmode='browse')
        headings={'checked':'选择','source':'网站','name':'商品名称','type':'商品类型','price':'网站原价 USD','stock':'库存','projects':'已有项目'}
        widths={'checked':55,'source':90,'name':300,'type':100,'price':105,'stock':80,'projects':200}
        for col in cols:tree.heading(col,text=headings[col]);tree.column(col,width=widths[col],anchor='center' if col!='name' else 'w')
        sy=ttk.Scrollbar(table_frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=sy.set)
        tree.pack(side='left',fill='both',expand=True);sy.pack(side='right',fill='y')
        count_var=tk.StringVar(value='已勾选 0 件')
        footer=ttk.Frame(win,padding=12);footer.pack(fill='x')
        ttk.Label(footer,textvariable=count_var).pack(side='left')
        def refresh_rows(*_):
            tree.delete(*tree.get_children())
            src='' if source_var.get()=='全部网站' else source_var.get()
            rows=self.store.products_for_management(source=src,membership='all',search=search_var.get().strip(),limit=50000)
            for row in rows:
                if row['status']=='excluded':continue
                pid=str(row['id'])
                tree.insert('','end',iid=pid,values=('☑' if pid in selected else '☐',row['source'],row['name'],row['product_type'],row['raw_usd'],row['stock'] if row['stock'] is not None else '未知',row['project_names'] or '—'))
            count_var.set(f'已勾选 {len(selected)} 件')
        def toggle(event):
            if tree.identify('region',event.x,event.y)!='cell':return
            if tree.identify_column(event.x)!='#1':return
            iid=tree.identify_row(event.y)
            if not iid:return
            if iid in selected:selected.remove(iid)
            else:selected.add(iid)
            values=list(tree.item(iid,'values'));values[0]='☑' if iid in selected else '☐';tree.item(iid,values=values)
            count_var.set(f'已勾选 {len(selected)} 件')
        tree.bind('<Button-1>',toggle)
        search_var.trace_add('write',refresh_rows);source_var.trace_add('write',refresh_rows)
        def select_visible():
            for iid in tree.get_children():selected.add(iid)
            refresh_rows()
        def clear_visible():
            for iid in tree.get_children():selected.discard(iid)
            refresh_rows()
        def save():
            if not selected:
                if not messagebox.askyesno('确认','当前没有勾选商品。仍然保留空项目吗？',parent=win):return
            ids=[int(x) for x in selected]
            self.store.project_assign(project_id,ids)
            win.destroy();self.refresh_all();self.status.set(f'项目「{project_name}」已加入 {len(ids)} 件商品')
        ttk.Button(footer,text='全选当前筛选结果',command=select_visible).pack(side='left',padx=4)
        ttk.Button(footer,text='取消当前筛选结果',command=clear_visible).pack(side='left',padx=4)
        ttk.Button(footer,text='确认加入项目',command=save).pack(side='right',padx=4)
        ttk.Button(footer,text='稍后选择',command=win.destroy).pack(side='right',padx=4)
        refresh_rows()

    def assign_products_to_current_project(self):
        pid=self._project_id();ids=self.goods.selection()
        if not pid or not ids:return messagebox.showinfo('提示','先选择当前项目，再到商品数据库选择商品')
        self.store.project_assign(pid,ids);self.refresh_all();self.status.set(f'已将 {len(ids)} 件商品加入当前项目')

    def assign_products(self):
        target=getattr(self,'goods_target_project',None)
        pid=self._project_id(target.get() if target and target.get() else None);ids=self.goods.selection()
        if not pid or not ids:return messagebox.showinfo('提示','先选择项目，再前往商品数据库选中商品')
        self.store.project_assign(pid,ids);self.refresh_projects();self.status.set(f'已添加 {len(ids)} 件商品到项目')

    def remove_project_products(self):
        pid=self._project_id();ids=[int(x) for x in self.project_table.selection()]
        if not pid or not ids:return messagebox.showinfo('提示','请先选择项目商品')
        if not messagebox.askyesno('确认移除',f'从当前项目移除 {len(ids)} 件商品？商品不会从总数据库删除。'):return
        self.store.project_remove(pid,ids);self.refresh_all();self.status.set('已从当前项目移除商品；若无其他项目关联，将回到待归类。')

    def apply_project_sort(self):
        pid=self._project_id()
        if not pid:return
        mapping={'手动固定顺序':'manual','本日销量从高到低':'sales_24h','本周销量从高到低':'sales_7d','本月销量从高到低':'sales_30d','价格从低到高':'price_asc','价格从高到低':'price_desc','库存从低到高':'stock_asc','库存从高到低':'stock_desc'}
        try:self.store.project_set_sort_mode(pid,mapping[self.project_sort_var.get()]);self.refresh_projects()
        except Exception as e:messagebox.showerror('排序失败',str(e))

    def toggle_project_capture(self):
        pid=self._project_id();ids=[int(x) for x in self.project_table.selection()]
        if not pid or not ids:return messagebox.showinfo('提示','请先选择项目商品')
        rows={r['id']:r for r in self.store.project_products(pid)}
        hide=any(rows[i]['include_in_capture'] for i in ids if i in rows)
        self.store.project_set_capture(pid,ids,not hide);self.refresh_projects()
        self.status.set('已更新所选商品的截图显示状态')

    def toggle_project_oos(self):
        pid=self._project_id()
        if not pid:return
        row=self.store.conn.execute('SELECT include_out_of_stock FROM projects WHERE id=?',(pid,)).fetchone()
        enabled=not bool(row['include_out_of_stock']) if row else False
        self.store.project_set_include_out_of_stock(pid,enabled)
        self.status.set('项目缺货商品截图状态：'+('显示' if enabled else '隐藏'))

    def move_project_product(self,direction):
        pid=self._project_id();ids=self.project_table.selection()
        if not pid or len(ids)!=1:return messagebox.showinfo('提示','请选择一件商品后上移或下移')
        rows=self.store.project_products(pid);order=[r['id'] for r in rows]
        item=int(ids[0]);idx=order.index(item);new=idx+direction
        if new<0 or new>=len(order):return
        order[idx],order[new]=order[new],order[idx]
        self.store.project_set_sort_mode(pid,'manual');self.store.project_set_order(pid,order)
        self.refresh_projects();self.project_table.selection_set(str(item))

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
        return (self.sales_period_var.get(),)

    def _load_sales_periods(self):
        pid=self._project_id(self.render_project.get())
        if pid and hasattr(self,'sales_period_var'):
            self.sales_period_var.set(self.store.get_project_periods(pid)[0])

    def _save_sales_periods(self):
        pid=self._project_id(self.render_project.get())
        if not pid:return messagebox.showinfo('提示','请先创建并选择项目')
        self.store.set_project_periods(pid,(self.sales_period_var.get(),));self.status.set('已保存单一销量展示周期')

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
            project_opts=self.store.conn.execute('SELECT include_out_of_stock FROM projects WHERE id=?',(pid,)).fetchone()
            paths=render_project(records,proj['name'],self.settings['screens_dir'],
                                 title=self.render_title.get() or '商品报价',footer=self.render_footer.get(),
                                 include_oos=bool(project_opts['include_out_of_stock']) if project_opts else True, sales_periods=periods,sales_by_product=self.store.project_sales(pid))
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
