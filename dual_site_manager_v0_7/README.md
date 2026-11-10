# 黑盒铺子 · 双站商品管理中心 v0.6（Windows 开发测试版）

## 本次交付内容

- 白色/浅蓝桌面 UI 基础实现：顶部状态条、左侧导航、10 个功能页面入口，包括总览、全站采集、商品数据库、项目、采集任务、截图、Telegram、报表、系统设置，以及单链接故障诊断。
- SQLite 原始商品与展示字段隔离：`products.name` / `raw_usd` / `stock` 是源数据；`products.display_name` / `display_usd` 是全局用户覆盖；`project_products.custom_name` / `custom_usd` 是项目级覆盖。
- 显示值优先级：项目专属 > 全局自定义 > 网站原始。采集更新不覆盖用户名称和售价。
- 商品数据库和项目页面提供独立改名/改价窗口，支持留空恢复跟随上层配置。
- 手动截图和定时任务共用同一白色报价渲染器。图片使用最终展示名称/价格、原站有效库存；当前导出仍属基础白色表格，不是高清 UI 设计稿的像素级复刻。
- v0.5 的网页列表发现、任务调度与 Telegram Bot API 模块保留，**真实网站动态列表采集准确率、项目定向更新与 Telegram 投递仍未进行 Windows 实站验收**。

## Windows 安装包

本 ZIP 是源码和 GitHub Actions Windows 构建工程，不是可直接安装的 Setup.exe。
解压后将 `.github/workflows/windows-installer.yml` 放到 GitHub 仓库根目录的对应路径，并上传 `dual_site_manager_v0_6` 文件夹。
GitHub Actions 的工作流明确定位 `v0_6` 文件夹，在 Windows 环境用 Python 3.12、PyInstaller、Inno Setup 构建。
成功后下载构建产物 `DualSiteInventory-Windows-Setup`，其中预期有 `DualSiteInventory_Setup_v0.6.0.exe`。
不要混用旧版 v0.5 的 workflow：它会选错目录。也无需删除旧版安装程序；升级前先备份本地数据。

## 数据与安全

旧数据库升级时采用添加字段的迁移方式，不删除旧表；为防止意外仍请先备份数据库。配置和数据库保存在用户可配置的目录，而不是安装程序目录。
定时采集和截图在 Windows 端的网络行为依赖网站允许的公开页面结构；碰到 CAPTCHA 或访问限制暂停并人工处理，不提供绕过功能。
库存减少只能作为**估算销量**；库存增加为**观察到的补货**。不应在没有完整快照时声称是准确销售订单数。
截图和 Telegram 发布使用项目有效展示值，不能用自定义显示名称作为采集匹配键。

## 本地验证

执行：`python -m unittest discover -s tests -v`；以及 `python -m py_compile *.py`。
本地构建环境已通过 21 项测试和虚拟显示器的 Tkinter 启动烟测；Windows 实机安装与网站联调未完成。

## 旧版说明（历史）

# 双站商品管理中心 v0.5 — 全站发现 + 定时截图 + Telegram 发布

本工程由 v0.2 继续开发，保留 SQLite、商品审核/排除、项目独立定价、截图自定义保存位置，以及 Windows 安装器。

## 已实现（代码层面）

- FB1314 和 CEOACC 分别进行网站首页、分类链接、分页及商品列表的**有界公开页面扫描**。
- 自动识别并尝试关闭 FB1314 的「继续 Continue」公告、CEOACC 的「不再显示」通知。
- 商品列表卡片 / 商品列表两种解析路径：仅在找到可靠商品名称、数字库存和明确 USD 价格时入库。
- 自动保存来源、原网站链接、商品 ID、价格、库存、历史快照；新品默认待审核。
- 用户选择 active / paused / excluded，后两者不会被定时刷新重新启用。
- 定时任务：`discover` 发现商品、`refresh` 更新激活商品库存、`capture` 渲染 PNG、`publish` 渲染 PNG 并通过 Telegram Bot API 发布。
- 发布图片可分多页；每个项目单独配置定时任务、发送对象和配文；Bot Token 使用 Windows DPAPI 加密保存。
- Windows 自定义数据库、截图、备份目录；安装器配置；现有数据库表向后兼容添加自动任务表。

## 重要边界

- **尚未在用户 Windows + FlClash 网络下对这两站完成全站扫描与采集字段的实站联调**。特别是 CEOACC 某些商品/多规格可能仅在交互式商品弹窗中显示，可能不会暴露链接或可确定的数字库存；这些商品会被跳过，不会造数据。
- “全站”功能的实际覆盖范围取决于网站公开导航、分类分页是否可访问，以及网站使用规则。每次任务会提供访问数、写入数、失败数和是否截断，并保存诊断截图和失败日志。
- 本版本 Telegram 发布支持 **Bot Token / Bot API**；**不支持 Telegram 个人账号手机登录或扫码登录**。必须先在 Telegram 创建 Bot、加入要发布的群/频道并授予发布权限。没有真实权限不能发布。
- 定时任务仅在软件运行时执行；电脑睡眠或关闭时不会执行；不保证 Telegram 网络故障后 exactly-once 投递。
- 当前构建工程须在 Windows/GitHub Actions 上生成真正的 Setup.exe；Linux 环境不能对最终 EXE 做 Windows 实机验收。
- 不自动绕过验证码、安全验证、访问控制或网站反爬措施，不应高频抓取；建议遵守站点规则。

## Windows 使用

安装后：

1. 在「全站与自动化」点击「立即全站扫描 FB1314」或「立即全站扫描 CEOACC」。**不需要逐条粘贴商品链接**。
2. 在「商品数据库」筛选待审核商品，将需要的商品勾选为「启用采集」，不需要的选择「永久排除」。
3. 在「项目与定价」新建项目、加入商品、设置项目独立 USD 售价。
4. 在「全站与自动化」创建 `discover`（新品发现）和 `refresh`（库存更新）任务；建议初期至少每 60 分钟一次，具体以网站许可为准。
5. 创建 `capture` 截图任务，选择项目、间隔分钟；截图将自动存到「系统与文件夹」设置的截图目录。
6. 在 Telegram BotFather 创建 Bot，并将它加入有权发布的群组/频道；在软件点击「保存 Telegram Bot Token」录入，不要上传到 GitHub。
7. 新建 `publish` 任务，选择项目、频道/群组 ID、间隔与文案。可先选择任务点击「立即执行选中任务」验证。

### 数据与升级

- 数据库：`Documents/DualSiteInventory/Database/inventory.sqlite3`（可以在软件设置中修改）。
- 截图：`Documents/DualSiteInventory/Screenshots`。
- 采集截图：`Documents/DualSiteInventory/Diagnostics`。
- 扫描错误日志：`Documents/DualSiteInventory/ScanLogs`。
- API 访问和正式 Token 不存入 GitHub 源代码。升级前建议用软件中的「立即备份数据库」创建备份。

### 开发构建

- `requirements.txt` 依赖 Pillow、Playwright 和 PyInstaller。
- Windows 下可运行 `build_installer.py`，使用 `installer/DualSite.iss` 和 Inno Setup 构建 Setup.exe。
- `.github/workflows/windows-installer.yml` 使用短路径 `C:\ds`，避免旧版 Inno Setup 压缩路径故障。
- `python -m unittest discover -s tests -v` 执行测试。


## v0.5 列表优先扫描策略

- 点击「全站与自动化」→「立即全站扫描」后，从主页/公开分类开始，分段滚动加载商品。
- 每轮约 1.8 秒等待加载（作为保守初值，实际站点请测试并按网站允许频率调整），连续多轮滚动位置与候选数不变才停止；单分类最多 180 轮。
- 优先从商品卡片或库存/价格表格一次读取名称、USD 价格和库存；不逐个点击商品详情。
- 列表缺失价格、库存或稳定识别时不猜测并跳过，按扫描日志检查；多规格商品可能需要后续网站专用适配。
- 首次发现商品仍进「待审核」；后续库存刷新重新扫描列表，仅更新启用商品。
- 上限、网页不可达、安全验证和页面结构变化会标记不完整，不宣称全站 100% 覆盖。
- 实际网站 CSS、滚动容器、网络流量与覆盖率尚需在 Windows + FlClash 中联调。
- v0.5 工程含 Windows 自动构建配置，并非已编译或实机验证的安装包。


## v0.5 FB1314 0 商品专项诊断

- 修正 FB1314 `?category_id=12` 等分类导航链接识别，避免漏掉分类入口。
- 网页首次加载后额外等待客户端商品列表渲染，降低过早读取造成的 0 商品。
- 在原有商品卡片选择器外，新增价格与库存相邻 DOM 节点的容器发现模式，兼容部分未使用常见 CSS 名称的布局。
- 当某个页面扫描到 0 条可信完整商品时，自动在 `Documents/DualSiteInventory/Diagnostics/<站点>/` 留下 `empty_*.png` 和对应 `empty_*.json`。JSON 仅含 URL、标题、候选数量和滚动统计，不包含 Cookie/Token 或整页 HTML。
- **注意**：这些修补是基于公开页面结构和本地测试作出的；由于当前执行环境不能运行目标站点真实交互式浏览器，尚未实测两个网站的动态 JS 卡片。因此 v0.5 仍属于修复测试版，不能保证 0 商品问题已经彻底解决。
- 如果仍然写入 0，优先提供 `empty_*.png` 与 `empty_*.json`（检查有无私人信息后再上传），这样可以精确定位页面渲染与选择器问题。


## v0.7 采集任务 UI 更新
- 四种任务类型中文化：全站扫描建库/同步、刷新已启用商品、项目定时截图、Telegram 定时发布。
- 采集周期直接填写小时，可设置 2、6 小时或任意 1–720 小时，后端以分钟持久化。
- 全站扫描实时显示已访问页面、候选商品、待核实字段、失败页和滚动次数；总量未知不显示虚假的百分比。
- 采集可请求停止，当前页面操作结束后中断任务，结果标记未完成。
- 全站任务与项目更新/截图/发布独立。CEOACC 页面字段仍需实站验证。
