# 黑盒铺子 v2.2.0 候选版

## 本轮改造
- CEOACC 商品列表采用更长的动态加载等待和 DOM 稳定检测；滚动间隔至少 1.25 秒，扫描时间预算提高至 240 秒。
- 采集诊断 JSON 增加多级保存目录回退，并写入 scan_history.jsonl。
- 采集任务生成 JSONL 执行日志，可在「采集日志」页面查看。
- 「采集任务管理」只管理网站类目发现、选定类目采集和库存刷新。
- 「截图模板管理」独立管理定时截图与 Telegram 定时发布。
- 采集任务与截图模板任务均可指定首次开始时间；循环周期分别限制为 1–24 小时、12–24 小时。
- 新增 SQLite start_at 兼容迁移，不删除现有商品、项目和自定义价格。

## 诊断文件
优先保存到数据库目录旁的 `Diagnostics/<site>/`；不可写时依次回退到：
1. `%USERPROFILE%\Documents\DualSiteInventory\Diagnostics\<site>`
2. `%LOCALAPPDATA%\DualSiteInventory\Diagnostics\<site>`
3. 系统临时目录 `DualSiteInventory\Diagnostics\<site>`

采集日志同样有多级回退，文件为 `Logs\collection\<site>_YYYYMMDD.jsonl`。

## 重要限制
本版本没有声称已经完成 FB1314 / CEOACC 实站覆盖验收。CEOACC 的等待和滚动策略已加强，但仍需在用户 Windows 环境运行，结合实际诊断报告核对动态页面结构。销量仍是库存快照估算，不等同网站真实成交量。
