# 黑盒铺子 v2.1.3 候选版

Windows 桌面端双站商品库存监控、项目管理、表格截图与 Telegram 自动发布工具。

> 当前交付为 v2.1.3 候选源代码包。FB1314 / CEOACC 实站全站覆盖、CEOACC 列表结构、Windows 安装包及 Telegram 群组端到端发布仍须在用户实际网络环境验收；不能把单元测试通过等同于实站采集已经验收。

## 本批已实现

- SQLite 原始商品与展示覆盖字段分离；来源、商品 ID、规格 ID 是采集匹配键。
- 网站原始类目独立管理：待选择、正在采集、已暂停、已排除四个分区；只允许启用类目写入正式库存数据。
- 商品管理增加归类状态视图：待归类、已归类、已排除；归类状态由项目关联计算，不与网站采集状态混为一谈。
- 一个商品可以加入多个项目；从某项目移除不会删除原始商品，最后一个项目关联移除后自动回到待归类视图。
- 项目可单独设置展示名称、售价、截图显示开关、手动序号和自动排序（销量/价格/库存）。
- 商品总览支持按来源、类型、归类状态、名称、价格、库存、24h/7天/30天估算销量排序。
- 批量归类、批量改价和状态操作；商品排除后不会继续出现在项目截图。
- 截图销量周期严格单选：24h / 7d / 30d。旧数据库中原先多选的设置升级时保留第一项。
- PNG 模板为蓝白简洁表格：序号、商品名称、价格、现货库存、所选的一种销量；商品名称列加宽，最多两行换行，自动分页。
- 没有项目销售价时禁止对外截图，绝不回退网站原价。
- 网站采集任务 UI 限定 1–24 小时；截图和 Telegram 发布 UI 限定 12–24 小时。仍可在任务中设置固定每日执行时间。
- 旧 SQLite 数据库采用增量迁移，不要求清空数据库。

## 本批未宣称已验收

- FB1314 / CEOACC 真实商品总数、完整列表滚动停止条件及所有类目覆盖率。
- CEOACC 页面可能需要登录态、动态列表或页面结构适配；目前不能凭空推断缺失价格/库存。
- 商品类型优先使用采集记录类型，缺失时暂以网站原始类目标题作为分类类型；需按实际站点类目校正。
- 自动任务需要 Windows 常驻运行；电脑关机、休眠期间不能保证按时执行。
- Telegram 仍使用 Bot API，需要配置 Bot Token 并将 Bot 加入目标群组/频道且授予发消息权限；不含个人账号登录。
- GitHub Actions Windows 构建尚未在本次环境执行；本地测试通过不代表安装 EXE 已生成。

## 开发与测试

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

## Windows 安装包

GitHub Actions 工作流：`.github/workflows/windows-installer.yml`。
在 GitHub 仓库的 Actions 页面运行 `Build BlackBoxShop v2.1 Windows installer`，成功后下载 `BlackBoxShop-v2.1-Windows-Setup` artifact。

## 数据安全

升级前先退出旧程序并备份 `Documents/DualSiteInventory/Database/inventory.sqlite3`、`%APPDATA%/DualSiteInventory/settings.json` 及截图目录。升级程序不会主动清空旧数据库。首次升级会增加数据库字段；请保留备份直到验收完成。


## v2.1 改造说明（本次源码更新）

- 新建项目后立即打开商品勾选窗口，可按名称搜索、按网站筛选、全选当前筛选结果或取消当前筛选结果。
- 同一商品仍可加入多个项目；已在其他项目中的商品仍可勾选。
- 新增销量窗口连续性保护：窗口边界快照缺失或采集间隔超过 27 小时时，返回数据不足，不将不完整历史显示为销量估算。
- 本次更新不宣称已完成 FB1314 / CEOACC 实站覆盖率验证；扫描结果仍按程序的 coverage 状态报告。

## v2.1 后续可靠性修订（2026-11-17）

- 采集完整性闸门现在同时检查滚动截断、页面失败、空结果、停止信号及缺少必要字段的商品卡片；不完整批次不写入库存快照。
- 销量窗口的最新数据新鲜度根据实际采集间隔自适应，兼容 6/12/24 小时采集计划；仍保留 27 小时最大采集间隔保护，避免长时间断采被当成零销量。
- Telegram 多页图片逐页记录成功/失败、消息 ID 和批次页码；同一计划任务批次重试时跳过已确认成功的页，减少重复发布。
- SQLite 通过追加字段迁移旧版 `publish_log`，不删除既有商品、项目或历史快照。

验证范围：本地单元测试覆盖采集闸门、6 小时采集间隔销量窗口和 Telegram 分页续传。此处不代表已完成 FB1314 / CEOACC 实站全站覆盖或真实 Telegram 群组端到端验证。


## v2.1.1 reliability patch (2026-11-17)

- Management-table sales columns and sales sorting now use the same rolling-window estimator as project views; the former fixed three-hour SQL freshness check is removed.
- Sales estimates require a baseline before the window, a recent terminal observation, and no sampling gap beyond a tolerance derived from the observed cadence (capped at 27 hours).
- The first stock-delta interval crossing the rolling-window start is excluded because its decline cannot be reliably allocated to the requested period.
- Incomplete scheduled catalogue scans now raise a task error after recording the failed scan; they do not appear as successful scheduled runs.
- Non-product navigation headings are no longer counted as incomplete product cards unless there is product identity or explicit price/stock evidence.

These checks are offline/unit-test validations. They do not certify live catalogue coverage on FB1314 or CEOACC, nor Telegram delivery in a real channel.


## v2.1.3 pagination reliability update (2026-11-17)

- Added conservative same-site pagination discovery for explicit `rel=next`, next-labelled controls, and numbered links inside known pagination containers.
- Pagination is followed for both full catalogue scans and explicitly enabled category scans. In selected-category mode, unrelated category discovery remains disabled.
- Product-detail URLs and off-site URLs are rejected; product detail pages are never opened by this pagination mechanism.
- Added regression tests for next-page links, numbered pagination links, and rejection of product/off-site links.
- This is still a candidate build: real-site pagination markup and total catalogue coverage must be checked in the user's browser/network environment. The code does not claim full-site coverage solely because pagination controls stop appearing.


## v2.1.3 scheduler reliability update (2026-11-17)

- Added SQLite `BEGIN IMMEDIATE` job claiming with a lease, preventing two running desktop instances from launching the same due automation task concurrently.
- Expired claims can be recovered after an application crash; completion clears the claim and advances the next schedule.
- Claim release is token-scoped so one process cannot release another process's active claim.
- Added multi-connection tests for duplicate prevention, lease recovery, completion cleanup, and token-scoped release.
- This is a local code-level reliability improvement; it does not verify live site coverage or Telegram delivery.

## v2.1.4 consolidated reliability pass (2026-11-17)

- Replaced the fixed catalogue wait with an adaptive DOM signal wait (visible price + stock + product-like rows, or an explicit end-of-list marker). This reduces unnecessary fixed delays but does not treat an empty list as successful.
- Every site scan now writes a compact JSON diagnostic report containing visited public catalogue URLs, page titles, category/pagination link counts, coverage stats, product count, and a bounded error list. It deliberately excludes cookies, credentials, and full page HTML.
- Successful scan messaging explicitly states that coverage represents visible public catalogue pages, not hidden or login-restricted inventory.
- Windows packaging now stages the PyInstaller bundle under the shorter `C:\\b\\app` path, checks the actual Chromium executable exists, compiles from that same staged directory, and uploads build logs even if the job fails.
- Installer version and artifact name are aligned at 2.1.4. Existing AppId is preserved so an in-place upgrade can target the same application identity.

Validation: offline unit tests only. The public pages were inspected for visible category structure; FB1314 exposes category links using `category_id`, while CEOACC exposes category links using `category` query parameters and a separate self-select inventory widget with page controls. The browser adapter still requires a Windows run in the user's normal network/session to prove exact live product-card parsing and full visible catalogue coverage. No CAPTCHA or login bypass is implemented. A successful scroll/pagination stop is not proof of private or hidden inventory completeness.
