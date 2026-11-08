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
