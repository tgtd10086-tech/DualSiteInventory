# 黑盒铺子 v2.0 开发版

Windows 桌面端双站商品库存监控、项目管理、表格截图与 Telegram 自动发布工具。

> 当前交付为 v2.0 开发源代码包。FB1314 / CEOACC 实站全站覆盖、CEOACC 列表结构、Windows 安装包及 Telegram 群组端到端发布仍须在用户实际网络环境验收；不能把单元测试通过等同于实站采集已经验收。

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
在 GitHub 仓库的 Actions 页面运行 `Build BlackBoxShop v2.0 Windows installer`，成功后下载 `BlackBoxShop-v2.0-Windows-Setup` artifact。

## 数据安全

升级前先退出旧程序并备份 `Documents/DualSiteInventory/Database/inventory.sqlite3`、`%APPDATA%/DualSiteInventory/settings.json` 及截图目录。升级程序不会主动清空旧数据库。首次升级会增加数据库字段；请保留备份直到验收完成。
