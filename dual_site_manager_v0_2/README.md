# 双站库存管理 v0.2（Windows 开发测试版）

这是用于继续开发的 **源代码包**，不是已经完成的生产软件，也不是已验证运行的 Windows EXE。原有 v0.1 的 SQLite、CSV 导入、新品审核、商品暂停/排除、项目单独定价、图片输出及自选文件夹均保留。**CEOACC API / API Key 模式已经从应用移除**。

## 新增内容

- FB1314 和 CEOACC 改为 **浏览器页面采集**。用户手动输入具体的 HTTPS 商品详情链接，每行一条，软件以 Playwright Chromium 打开页面。
- FB1314 的公告弹窗：仅尝试点击文字完全匹配 `继续 Continue`、`Continue`、`继续` 的控件。
- CEOACC 的通知弹窗：先尝试 `不再显示`，再尝试 `关闭`。
- 普通弹窗不存在时继续执行。验证码、反机器人安全验证不会被绕过；浏览器默认可见，便于用户处理需要人工完成的交互。
- 各网站独立持久化浏览器资料，保留站点正常写入的偏好 / Cookie；切勿与他人分享资料目录。
- 未能确认商品名称、**USD 原价**、库存、商品 ID 时，**不写入数据库**。失败保留诊断截图并显示错误。
- 商品暂停/永久排除时，再次采集不会更新这些商品。

## 安装与运行

1. Windows 10/11 安装 Python 3.11 或 3.12，并启用 Add Python to PATH。
2. 解压 ZIP，运行 `install_browser_windows.bat` 安装 Pillow、Playwright、Chromium、PyInstaller。该步骤需要访问软件发行源。
3. 双击 `start_windows.bat` 启动桌面应用。
4. 在「网站采集」页输入对应网站的**实际商品详情页链接**，点击采集按钮。第一次会打开 Chromium 浏览器窗口。
5. 在「商品数据库」查看采集结果；新品默认为 `review`，需人工启用。
6. 如果无法解析，检查数据目录同级的 `Diagnostics/<website>/` 下诊断截图。
7. `build_windows.bat` 是 Windows 打包脚本，但构建和运行效果尚未在真实 Windows 机器上验证。Playwright 的 Chromium 仍需通过安装脚本预先安装在该机器上。

## 核心限制（务必了解）

- **CEOACC 的实际商品详情 DOM 结构未完成真实页面联调。** 目前仅当商品页存在完整的 schema.org JSON-LD Product 数据（包括唯一 SKU/ID、明确 `priceCurrency=USD`、数值 `inventoryLevel`）时才能导入；否则会保存诊断截图，不做臆测。该适配器后续需要结合真实页面结构继续实现。
- FB1314 的浏览器采集目前仅支持符合 `/goods/数字.html` 的单商品链接，解析库存与价格依赖可见文字结构，后续需实测。
- 没有全站商品发现、自动分页、后台定时任务、销售/补货高级报表，也没有 Telegram 登录或定时自动发送；这些功能仍在 V1.0 计划中。
- 不会自动确认登录、做购买操作、绕过 CAPTCHA 或网站限制；请遵守网站的使用政策和合理频率。
- v0.2 只能访问明确允许的网站 HTTPS 链接，不会接受任意第三方站点。
- 数据存储位置从设置选择；数据库当前使用 SQLite；备份功能保留。

## 本地测试

`python -m unittest discover -s tests -v`

单元测试不能代替 Windows 环境测试或真实网站联调。
